import os
from datetime import datetime, timedelta
from models import (ReleaseRequest, RollbackRecord, MonitorRecord,
                     WeeklyReport, get_session)
from audit_logger import AuditLogger
import config
import random


class WeeklyReportManager:
    @staticmethod
    def generate_weekly_report(week_start=None, week_end=None):
        if week_start is None or week_end is None:
            now = datetime.now()
            current_weekday = now.weekday()
            week_start = now - timedelta(days=current_weekday + 7)
            week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
            week_end = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)

        session = get_session()
        try:
            releases = session.query(ReleaseRequest).filter(
                ReleaseRequest.submit_time >= week_start,
                ReleaseRequest.submit_time <= week_end
            ).all()

            total_releases = len(releases)
            successful_releases = len([r for r in releases if r.status in ['approved', 'grayscaling', 'fully_released']])
            release_success_rate = (successful_releases / total_releases) if total_releases > 0 else 0.0

            rollbacks = session.query(RollbackRecord).filter(
                RollbackRecord.start_time >= week_start,
                RollbackRecord.start_time <= week_end
            ).all()
            rollback_count = len(rollbacks)

            monitors = session.query(MonitorRecord).filter(
                MonitorRecord.monitor_time >= week_start,
                MonitorRecord.monitor_time <= week_end
            ).all()

            if monitors:
                avg_claim_duration = sum(m.claim_process_delay_seconds for m in monitors) / len(monitors)
                avg_uw_pass_rate = sum(m.underwriting_pass_rate for m in monitors) / len(monitors)
                avg_claim_abnormal_rate = sum(m.claim_abnormal_rate for m in monitors) / len(monitors)
            else:
                avg_claim_duration = 0.0
                avg_uw_pass_rate = 0.0
                avg_claim_abnormal_rate = 0.0

            report = WeeklyReport(
                week_start=week_start,
                week_end=week_end,
                total_releases=total_releases,
                successful_releases=successful_releases,
                release_success_rate=round(release_success_rate, 4),
                rollback_count=rollback_count,
                avg_claim_process_duration=round(avg_claim_duration, 2),
                avg_underwriting_pass_rate=round(avg_uw_pass_rate, 4),
                avg_claim_abnormal_rate=round(avg_claim_abnormal_rate, 4)
            )
            session.add(report)
            session.flush()
            report_id = report.id

            pdf_path = WeeklyReportManager._generate_pdf(report, releases, rollbacks, monitors)
            excel_path = WeeklyReportManager._generate_excel(report, releases, rollbacks, monitors)

            report.pdf_path = pdf_path
            report.excel_path = excel_path
            session.commit()

            AuditLogger.log(
                operation_type='generate_weekly_report',
                operation_module='report',
                operator='system',
                operation_detail=f'生成周报: {week_start.strftime("%Y-%m-%d")} ~ {week_end.strftime("%Y-%m-%d")}',
                related_id=report_id,
                related_type='weekly_report',
                regulatory_related=True,
                risk_level='medium'
            )

            return {
                'report_id': report_id,
                'week_start': week_start.strftime('%Y-%m-%d'),
                'week_end': week_end.strftime('%Y-%m-%d'),
                'total_releases': total_releases,
                'successful_releases': successful_releases,
                'release_success_rate': release_success_rate,
                'rollback_count': rollback_count,
                'avg_claim_process_duration': avg_claim_duration,
                'pdf_path': pdf_path,
                'excel_path': excel_path
            }
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    @staticmethod
    def _generate_pdf(report, releases, rollbacks, monitors):
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.graphics.shapes import Drawing
        from reportlab.graphics.charts.barcharts import VerticalBarChart
        from reportlab.graphics.charts.linecharts import HorizontalLineChart

        pdf_filename = f'weekly_report_{report.week_start.strftime("%Y%m%d")}.pdf'
        pdf_path = os.path.join(config.REPORT_DIR, pdf_filename)

        doc = SimpleDocTemplate(pdf_path, pagesize=A4,
                                leftMargin=40, rightMargin=40,
                                topMargin=40, bottomMargin=40)
        styles = getSampleStyleSheet()
        story = []

        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Title'],
            fontSize=20,
            textColor=colors.darkblue,
            spaceAfter=20
        )
        story.append(Paragraph('保险核保理赔系统 - 合规运营周报', title_style))
        story.append(Paragraph(
            f'统计周期: {report.week_start.strftime("%Y年%m月%d日")} - {report.week_end.strftime("%Y年%m月%d日")}',
            styles['Normal']
        ))
        story.append(Spacer(1, 20))

        story.append(Paragraph('一、核心指标概览', styles['Heading2']))
        story.append(Spacer(1, 10))

        overview_data = [
            ['指标', '数值', '说明'],
            ['总发布次数', str(report.total_releases), '本周提交的发布申请总数'],
            ['发布成功次数', str(report.successful_releases), '通过审批并成功发布的数量'],
            ['发布成功率', f'{report.release_success_rate * 100:.2f}%', '成功发布 / 总发布'],
            ['回滚次数', str(report.rollback_count), '本周触发的合规回滚次数'],
            ['平均理赔处理时长', f'{report.avg_claim_process_duration / 60:.1f} 分钟', '所有监控样本均值'],
            ['平均核保通过率', f'{report.avg_underwriting_pass_rate * 100:.2f}%', '所有监控样本均值'],
            ['平均赔付异常率', f'{report.avg_claim_abnormal_rate * 100:.2f}%', '所有监控样本均值'],
        ]
        table = Table(overview_data, colWidths=[120, 100, 250])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
        ]))
        story.append(table)
        story.append(Spacer(1, 20))

        story.append(Paragraph('二、发布成功率趋势', styles['Heading2']))
        story.append(Spacer(1, 10))

        try:
            drawing = Drawing(450, 200)
            bar = VerticalBarChart()
            bar.x = 50
            bar.y = 50
            bar.height = 125
            bar.width = 350

            daily_data = WeeklyReportManager._get_daily_release_data(report.week_start, report.week_end)
            bar.data = [daily_data['success_rates']]
            bar.categoryAxis.categoryNames = daily_data['labels']
            bar.bars[0].fillColor = colors.green

            drawing.add(bar)
            story.append(drawing)
        except Exception as e:
            story.append(Paragraph(f'(图表生成说明: {str(e)})', styles['Normal']))

        story.append(Spacer(1, 20))

        story.append(Paragraph('三、理赔处理时长趋势', styles['Heading2']))
        story.append(Spacer(1, 10))

        try:
            drawing2 = Drawing(450, 200)
            line = HorizontalLineChart()
            line.x = 50
            line.y = 50
            line.height = 125
            line.width = 350

            daily_monitor = WeeklyReportManager._get_daily_monitor_data(report.week_start, report.week_end)
            line.data = [daily_monitor['claim_durations']]
            line.categoryAxis.categoryNames = daily_monitor['labels']
            line.lines[0].strokeColor = colors.red

            drawing2.add(line)
            story.append(drawing2)
        except Exception as e:
            story.append(Paragraph(f'(图表生成说明: {str(e)})', styles['Normal']))

        story.append(Spacer(1, 20))

        story.append(Paragraph('四、合规说明', styles['Heading2']))
        story.append(Spacer(1, 10))
        story.append(Paragraph('本报告数据来源于系统自动化监控，所有操作均记录于审计日志，', styles['Normal']))
        story.append(Paragraph('可直接用于银保监合规检查。', styles['Normal']))
        story.append(Spacer(1, 10))
        story.append(Paragraph(f'报告生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', styles['Normal']))

        doc.build(story)
        return pdf_path

    @staticmethod
    def _generate_excel(report, releases, rollbacks, monitors):
        import pandas as pd

        excel_filename = f'weekly_report_{report.week_start.strftime("%Y%m%d")}.xlsx'
        excel_path = os.path.join(config.REPORT_DIR, excel_filename)

        overview_data = {
            '指标': [
                '统计周期开始', '统计周期结束', '总发布次数', '发布成功次数',
                '发布成功率', '回滚次数', '平均理赔处理时长(秒)',
                '平均核保通过率', '平均赔付异常率'
            ],
            '数值': [
                report.week_start.strftime('%Y-%m-%d'),
                report.week_end.strftime('%Y-%m-%d'),
                report.total_releases,
                report.successful_releases,
                f'{report.release_success_rate * 100:.2f}%',
                report.rollback_count,
                report.avg_claim_process_duration,
                f'{report.avg_underwriting_pass_rate * 100:.2f}%',
                f'{report.avg_claim_abnormal_rate * 100:.4f}%'
            ]
        }
        df_overview = pd.DataFrame(overview_data)

        release_data = []
        for r in releases:
            release_data.append({
                '版本号': r.version,
                '标题': r.title,
                '风险级别': config.RISK_LEVEL_NAMES.get(r.risk_level, r.risk_level),
                '险种': ','.join([config.INSURANCE_TYPE_NAMES.get(it, it) for it in r.insurance_types]),
                '提交人': r.submitter,
                '提交时间': r.submit_time.strftime('%Y-%m-%d %H:%M:%S') if r.submit_time else '',
                '状态': r.status,
                '是否回滚': '是' if r.rollback_triggered else '否'
            })
        df_releases = pd.DataFrame(release_data) if release_data else pd.DataFrame(columns=['版本号', '标题', '风险级别', '险种', '提交人', '提交时间', '状态', '是否回滚'])

        rollback_data = []
        for rb in rollbacks:
            rollback_data.append({
                '回滚ID': rb.id,
                '发布ID': rb.release_request_id,
                '回滚类型': rb.rollback_type,
                '触发原因': rb.trigger_reason,
                '从版本': rb.rollback_from_version,
                '回滚至': rb.rollback_to_version,
                '影响保单数': rb.affected_policies_count,
                '开始时间': rb.start_time.strftime('%Y-%m-%d %H:%M:%S') if rb.start_time else '',
                '状态': rb.status
            })
        df_rollbacks = pd.DataFrame(rollback_data) if rollback_data else pd.DataFrame(columns=['回滚ID', '发布ID', '回滚类型', '触发原因', '从版本', '回滚至', '影响保单数', '开始时间', '状态'])

        daily_data = WeeklyReportManager._get_daily_release_data(report.week_start, report.week_end)
        df_daily = pd.DataFrame({
            '日期': daily_data['labels'],
            '发布数量': daily_data['release_counts'],
            '成功数量': daily_data['success_counts'],
            '成功率(%)': [f'{r * 100:.1f}' for r in daily_data['success_rates']]
        })

        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
            df_overview.to_excel(writer, sheet_name='概览', index=False)
            df_releases.to_excel(writer, sheet_name='发布明细', index=False)
            df_rollbacks.to_excel(writer, sheet_name='回滚明细', index=False)
            df_daily.to_excel(writer, sheet_name='每日统计', index=False)

        return excel_path

    @staticmethod
    def _get_daily_release_data(week_start, week_end):
        session = get_session()
        try:
            labels = []
            release_counts = []
            success_counts = []
            success_rates = []

            for i in range(7):
                day = week_start + timedelta(days=i)
                day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
                day_end = day.replace(hour=23, minute=59, second=59)

                day_releases = session.query(ReleaseRequest).filter(
                    ReleaseRequest.submit_time >= day_start,
                    ReleaseRequest.submit_time <= day_end
                ).all()

                total = len(day_releases)
                success = len([r for r in day_releases if r.status in ['approved', 'grayscaling', 'fully_released']])
                rate = success / total if total > 0 else 0.0

                labels.append(day.strftime('%m-%d'))
                release_counts.append(total)
                success_counts.append(success)
                success_rates.append(round(rate, 4))

            return {
                'labels': labels,
                'release_counts': release_counts,
                'success_counts': success_counts,
                'success_rates': success_rates
            }
        finally:
            session.close()

    @staticmethod
    def _get_daily_monitor_data(week_start, week_end):
        session = get_session()
        try:
            labels = []
            claim_durations = []
            uw_pass_rates = []

            for i in range(7):
                day = week_start + timedelta(days=i)
                day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
                day_end = day.replace(hour=23, minute=59, second=59)

                day_monitors = session.query(MonitorRecord).filter(
                    MonitorRecord.monitor_time >= day_start,
                    MonitorRecord.monitor_time <= day_end
                ).all()

                if day_monitors:
                    avg_delay = sum(m.claim_process_delay_seconds for m in day_monitors) / len(day_monitors)
                    avg_pass = sum(m.underwriting_pass_rate for m in day_monitors) / len(day_monitors)
                else:
                    avg_delay = 0.0
                    avg_pass = 0.0

                labels.append(day.strftime('%m-%d'))
                claim_durations.append(round(avg_delay, 2))
                uw_pass_rates.append(round(avg_pass, 4))

            return {
                'labels': labels,
                'claim_durations': claim_durations,
                'uw_pass_rates': uw_pass_rates
            }
        finally:
            session.close()

    @staticmethod
    def list_reports(page=1, page_size=20):
        session = get_session()
        try:
            query = session.query(WeeklyReport)
            total = query.count()
            reports = query.order_by(WeeklyReport.week_start.desc()) \
                .offset((page - 1) * page_size).limit(page_size).all()

            return {
                'total': total,
                'page': page,
                'page_size': page_size,
                'reports': [WeeklyReportManager._to_dict(r) for r in reports]
            }
        finally:
            session.close()

    @staticmethod
    def _to_dict(report):
        return {
            'id': report.id,
            'week_start': report.week_start.strftime('%Y-%m-%d'),
            'week_end': report.week_end.strftime('%Y-%m-%d'),
            'total_releases': report.total_releases,
            'successful_releases': report.successful_releases,
            'release_success_rate': report.release_success_rate,
            'rollback_count': report.rollback_count,
            'avg_claim_process_duration': report.avg_claim_process_duration,
            'avg_underwriting_pass_rate': report.avg_underwriting_pass_rate,
            'avg_claim_abnormal_rate': report.avg_claim_abnormal_rate,
            'pdf_path': report.pdf_path,
            'excel_path': report.excel_path,
            'generated_at': report.generated_at.strftime('%Y-%m-%d %H:%M:%S')
        }
