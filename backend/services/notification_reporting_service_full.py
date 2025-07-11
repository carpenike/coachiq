"""
Notification Reporting Service

This service provides advanced reporting capabilities for the notification system,
including scheduled reports, custom templates, and multiple export formats.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, BinaryIO
from uuid import uuid4

import matplotlib.pyplot as plt
import pandas as pd
from jinja2 import Environment, FileSystemLoader
from matplotlib.backends.backend_pdf import PdfPages
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select

from backend.models.notification import NotificationChannel, NotificationType
from backend.models.notification_analytics import (
    AggregationPeriod,
    MetricType,
)
from backend.services.database_manager import DatabaseManager
from backend.services.notification_analytics_service import NotificationAnalyticsService


class ReportTemplate:
    """Base class for report templates."""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    async def generate(
        self,
        analytics_service: NotificationAnalyticsService,
        start_date: datetime,
        end_date: datetime,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate report data."""
        raise NotImplementedError


class DailyDigestTemplate(ReportTemplate):
    """Daily digest report template."""

    def __init__(self):
        super().__init__("daily_digest", "Daily summary of notification activity and performance")

    async def generate(
        self,
        analytics_service: NotificationAnalyticsService,
        start_date: datetime,
        end_date: datetime,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate daily digest report."""
        # Get channel metrics
        channel_metrics = await analytics_service.get_channel_metrics(
            start_date=start_date, end_date=end_date
        )

        # Get hourly metrics
        hourly_metrics = await analytics_service.get_aggregated_metrics(
            MetricType.DELIVERY_COUNT, AggregationPeriod.HOURLY, start_date, end_date
        )

        # Get error analysis
        errors = await analytics_service.analyze_errors(
            start_date=start_date, end_date=end_date, min_occurrences=1
        )

        # Get queue health
        queue_health = await analytics_service.get_queue_health()

        return {
            "report_type": "daily_digest",
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
            "summary": {
                "total_sent": sum(cm.total_sent for cm in channel_metrics),
                "total_delivered": sum(cm.total_delivered for cm in channel_metrics),
                "total_failed": sum(cm.total_failed for cm in channel_metrics),
                "overall_success_rate": sum(cm.total_delivered for cm in channel_metrics)
                / max(sum(cm.total_sent for cm in channel_metrics), 1),
            },
            "channel_performance": [
                {
                    "channel": cm.channel.value,
                    "sent": cm.total_sent,
                    "delivered": cm.total_delivered,
                    "failed": cm.total_failed,
                    "success_rate": cm.success_rate,
                    "avg_delivery_time_ms": cm.average_delivery_time,
                }
                for cm in channel_metrics
            ],
            "hourly_activity": [
                {
                    "hour": metric.timestamp.hour,
                    "count": int(metric.value),
                }
                for metric in hourly_metrics
            ],
            "top_errors": [
                {
                    "error_code": err.error_code,
                    "channel": err.channel,
                    "occurrences": err.occurrence_count,
                    "affected_recipients": err.affected_recipients,
                    "recommendation": err.recommended_action,
                }
                for err in sorted(errors, key=lambda x: x.occurrence_count, reverse=True)[:5]
            ],
            "queue_health": {
                "queue_depth": queue_health.queue_depth,
                "processing_rate": queue_health.processing_rate,
                "health_score": queue_health.health_score,
            },
        }


class WeeklyAnalyticsTemplate(ReportTemplate):
    """Weekly analytics report template."""

    def __init__(self):
        super().__init__(
            "weekly_analytics", "Comprehensive weekly analytics with trends and insights"
        )

    async def generate(
        self,
        analytics_service: NotificationAnalyticsService,
        start_date: datetime,
        end_date: datetime,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate weekly analytics report."""
        # Get daily metrics for the week
        daily_metrics = await analytics_service.get_aggregated_metrics(
            MetricType.DELIVERY_COUNT, AggregationPeriod.DAILY, start_date, end_date
        )

        # Get channel metrics
        channel_metrics = await analytics_service.get_channel_metrics(
            start_date=start_date, end_date=end_date
        )

        # Get previous week for comparison
        prev_start = start_date - timedelta(days=7)
        prev_end = start_date
        prev_channel_metrics = await analytics_service.get_channel_metrics(
            start_date=prev_start, end_date=prev_end
        )

        # Calculate trends
        current_total = sum(cm.total_sent for cm in channel_metrics)
        prev_total = sum(cm.total_sent for cm in prev_channel_metrics)
        volume_trend = ((current_total - prev_total) / max(prev_total, 1)) * 100

        current_success = sum(cm.total_delivered for cm in channel_metrics) / max(current_total, 1)
        prev_success = sum(cm.total_delivered for cm in prev_channel_metrics) / max(prev_total, 1)
        success_trend = ((current_success - prev_success) / max(prev_success, 0.01)) * 100

        return {
            "report_type": "weekly_analytics",
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
            "summary": {
                "total_sent": current_total,
                "total_delivered": sum(cm.total_delivered for cm in channel_metrics),
                "total_failed": sum(cm.total_failed for cm in channel_metrics),
                "overall_success_rate": current_success,
                "volume_trend_percent": volume_trend,
                "success_trend_percent": success_trend,
            },
            "daily_breakdown": [
                {
                    "date": metric.timestamp.date().isoformat(),
                    "count": int(metric.value),
                }
                for metric in daily_metrics
            ],
            "channel_comparison": {
                "current_week": [
                    {
                        "channel": cm.channel.value,
                        "sent": cm.total_sent,
                        "success_rate": cm.success_rate,
                    }
                    for cm in channel_metrics
                ],
                "previous_week": [
                    {
                        "channel": cm.channel.value,
                        "sent": cm.total_sent,
                        "success_rate": cm.success_rate,
                    }
                    for cm in prev_channel_metrics
                ],
            },
            "insights": self._generate_insights(
                channel_metrics, prev_channel_metrics, volume_trend, success_trend
            ),
        }

    def _generate_insights(
        self,
        current: list,
        previous: list,
        volume_trend: float,
        success_trend: float,
    ) -> list[str]:
        """Generate insights from metrics."""
        insights = []

        if volume_trend > 20:
            insights.append(
                f"Notification volume increased by {volume_trend:.1f}% compared to last week"
            )
        elif volume_trend < -20:
            insights.append(
                f"Notification volume decreased by {abs(volume_trend):.1f}% compared to last week"
            )

        if success_trend > 5:
            insights.append(f"Delivery success rate improved by {success_trend:.1f}%")
        elif success_trend < -5:
            insights.append(
                f"Delivery success rate declined by {abs(success_trend):.1f}% - investigation recommended"
            )

        # Find worst performing channel
        worst_channel = min(current, key=lambda x: x.success_rate)
        if worst_channel.success_rate < 0.8:
            insights.append(
                f"{worst_channel.channel.value} channel has low success rate ({worst_channel.success_rate:.1%})"
            )

        return insights


class NotificationReportingService:
    """
    Advanced reporting service for notification analytics.

    Provides scheduled reporting, custom templates, and multiple export formats
    including JSON, CSV, and PDF with visualizations.
    """

    def __init__(
        self,
        database_manager: DatabaseManager,
        analytics_service: NotificationAnalyticsService,
    ):
        """
        Initialize the reporting service.

        Args:
            database_manager: Database manager for persistence
            analytics_service: Analytics service for data collection
        """
        self.db_manager = database_manager
        self.analytics_service = analytics_service
        self.logger = logging.getLogger(f"{__name__}.NotificationReportingService")

        # Report templates
        self.templates = {
            "daily_digest": DailyDigestTemplate(),
            "weekly_analytics": WeeklyAnalyticsTemplate(),
        }

        # Scheduled reports
        self._scheduled_reports: dict[str, dict[str, Any]] = {}
        self._scheduler_task: asyncio.Task | None = None
        self._running = False

        # Report storage
        self.reports_dir = Path("reports")
        self.reports_dir.mkdir(exist_ok=True)

        # Template environment for HTML/PDF generation
        self.jinja_env = Environment(loader=FileSystemLoader("templates/reports"), autoescape=True)

    async def start(self) -> None:
        """Start the reporting service."""
        if self._running:
            return

        self._running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())

        self.logger.info("NotificationReportingService started")

    async def stop(self) -> None:
        """Stop the reporting service."""
        if not self._running:
            return

        self._running = False

        if self._scheduler_task and not self._scheduler_task.done():
            self._scheduler_task.cancel()

        self.logger.info("NotificationReportingService stopped")

    async def generate_report(
        self,
        template_name: str,
        start_date: datetime,
        end_date: datetime,
        format: str = "json",
        parameters: dict[str, Any] | None = None,
        generated_by: str | None = None,
    ) -> NotificationReportModel:
        """
        Generate a report using a template.

        Args:
            template_name: Name of the report template
            start_date: Report period start
            end_date: Report period end
            format: Output format (json, csv, pdf, html)
            parameters: Additional report parameters
            generated_by: User who generated the report

        Returns:
            Generated report model
        """
        if template_name not in self.templates:
            raise ValueError(f"Unknown template: {template_name}")

        template = self.templates[template_name]

        # Generate report data
        report_data = await template.generate(
            self.analytics_service, start_date, end_date, parameters
        )

        # Create report model
        report_id = str(uuid4())
        report_model = NotificationReportModel(
            report_id=report_id,
            report_type=template_name,
            report_name=f"{template.description} - {start_date.date()} to {end_date.date()}",
            start_date=start_date,
            end_date=end_date,
            generated_by=generated_by,
            format=format,
            summary_data=report_data.get("summary", {}),
            parameters=parameters,
            is_scheduled=False,
        )

        # Generate report file
        file_path, file_size = await self._generate_report_file(
            report_id, report_data, format, template_name
        )

        report_model.file_path = str(file_path)
        report_model.file_size_bytes = file_size

        # Save to database
        async with self.db_manager.get_session() as session:
            session.add(report_model)
            await session.commit()

        return report_model

    async def schedule_report(
        self,
        schedule_id: str,
        template_name: str,
        schedule: dict[str, Any],
        format: str = "json",
        parameters: dict[str, Any] | None = None,
        recipients: list[str] | None = None,
    ) -> None:
        """
        Schedule a recurring report.

        Args:
            schedule_id: Unique schedule ID
            template_name: Report template to use
            schedule: Schedule configuration (cron expression or interval)
            format: Output format
            parameters: Report parameters
            recipients: Email recipients for the report
        """
        self._scheduled_reports[schedule_id] = {
            "template": template_name,
            "schedule": schedule,
            "format": format,
            "parameters": parameters or {},
            "recipients": recipients or [],
            "last_run": None,
            "next_run": self._calculate_next_run(schedule),
        }

        self.logger.info(f"Scheduled report {schedule_id} with template {template_name}")

    async def unschedule_report(self, schedule_id: str) -> None:
        """Remove a scheduled report."""
        if schedule_id in self._scheduled_reports:
            del self._scheduled_reports[schedule_id]
            self.logger.info(f"Unscheduled report {schedule_id}")

    async def get_report(self, report_id: str) -> NotificationReportModel | None:
        """
        Get a generated report by ID.

        Args:
            report_id: Report ID

        Returns:
            Report model or None if not found
        """
        async with self.db_manager.get_session() as session:
            stmt = select(NotificationReportModel).where(
                NotificationReportModel.report_id == report_id
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_report_file(self, report_id: str) -> tuple[Path, str] | None:
        """
        Get report file path and format.

        Args:
            report_id: Report ID

        Returns:
            Tuple of (file_path, format) or None
        """
        report = await self.get_report(report_id)
        if report and report.file_path:
            file_path = Path(report.file_path)
            if file_path.exists():
                return file_path, report.format

        return None

    async def list_reports(
        self,
        report_type: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        generated_by: str | None = None,
        limit: int = 100,
    ) -> list[NotificationReportModel]:
        """
        List generated reports with optional filters.

        Args:
            report_type: Filter by report type
            start_date: Filter by generation date start
            end_date: Filter by generation date end
            generated_by: Filter by generator
            limit: Maximum results

        Returns:
            List of report models
        """
        async with self.db_manager.get_session() as session:
            stmt = select(NotificationReportModel)

            if report_type:
                stmt = stmt.where(NotificationReportModel.report_type == report_type)
            if start_date:
                stmt = stmt.where(NotificationReportModel.created_at >= start_date)
            if end_date:
                stmt = stmt.where(NotificationReportModel.created_at <= end_date)
            if generated_by:
                stmt = stmt.where(NotificationReportModel.generated_by == generated_by)

            stmt = stmt.order_by(NotificationReportModel.created_at.desc()).limit(limit)

            result = await session.execute(stmt)
            return list(result.scalars().all())

    # File generation methods

    async def _generate_report_file(
        self,
        report_id: str,
        data: dict[str, Any],
        format: str,
        template_name: str,
    ) -> tuple[Path, int]:
        """Generate report file in specified format."""
        if format == "json":
            return await self._generate_json_report(report_id, data)
        if format == "csv":
            return await self._generate_csv_report(report_id, data)
        if format == "pdf":
            return await self._generate_pdf_report(report_id, data, template_name)
        if format == "html":
            return await self._generate_html_report(report_id, data, template_name)
        raise ValueError(f"Unsupported format: {format}")

    async def _generate_json_report(
        self,
        report_id: str,
        data: dict[str, Any],
    ) -> tuple[Path, int]:
        """Generate JSON report file."""
        file_path = self.reports_dir / f"{report_id}.json"

        content = json.dumps(data, indent=2, default=str)
        file_path.write_text(content)

        return file_path, len(content)

    async def _generate_csv_report(
        self,
        report_id: str,
        data: dict[str, Any],
    ) -> tuple[Path, int]:
        """Generate CSV report file."""
        file_path = self.reports_dir / f"{report_id}.csv"

        # Convert report data to CSV format
        rows = []

        # Summary section
        rows.append(["Report Summary"])
        for key, value in data.get("summary", {}).items():
            rows.append([key.replace("_", " ").title(), value])
        rows.append([])

        # Channel performance
        if "channel_performance" in data:
            rows.append(["Channel Performance"])
            channels = data["channel_performance"]
            if channels:
                headers = list(channels[0].keys())
                rows.append(headers)
                for channel in channels:
                    rows.append([channel.get(h, "") for h in headers])
            rows.append([])

        # Daily breakdown
        if "daily_breakdown" in data:
            rows.append(["Daily Activity"])
            rows.append(["Date", "Count"])
            for day in data["daily_breakdown"]:
                rows.append([day["date"], day["count"]])
            rows.append([])

        # Write CSV
        df = pd.DataFrame(rows)
        df.to_csv(file_path, index=False, header=False)

        return file_path, file_path.stat().st_size

    async def _generate_pdf_report(
        self,
        report_id: str,
        data: dict[str, Any],
        template_name: str,
    ) -> tuple[Path, int]:
        """Generate PDF report file with visualizations."""
        file_path = self.reports_dir / f"{report_id}.pdf"

        # Create PDF document
        doc = SimpleDocTemplate(
            str(file_path),
            pagesize=letter,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch,
        )

        # Get styles
        styles = getSampleStyleSheet()
        title_style = styles["Title"]
        heading_style = styles["Heading2"]
        normal_style = styles["Normal"]

        # Build story
        story = []

        # Title
        title = data.get("report_type", "Notification Report").replace("_", " ").title()
        story.append(Paragraph(title, title_style))
        story.append(Spacer(1, 0.2 * inch))

        # Period
        if "period" in data:
            period_text = f"Period: {data['period']['start']} to {data['period']['end']}"
            story.append(Paragraph(period_text, normal_style))
            story.append(Spacer(1, 0.2 * inch))

        # Summary
        if "summary" in data:
            story.append(Paragraph("Summary", heading_style))
            summary_data = [
                [key.replace("_", " ").title(), str(value)]
                for key, value in data["summary"].items()
            ]
            summary_table = Table(summary_data, colWidths=[3 * inch, 2 * inch])
            summary_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, 0), 12),
                        ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                        ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                        ("GRID", (0, 0), (-1, -1), 1, colors.black),
                    ]
                )
            )
            story.append(summary_table)
            story.append(Spacer(1, 0.3 * inch))

        # Channel performance
        if data.get("channel_performance"):
            story.append(Paragraph("Channel Performance", heading_style))

            # Create visualization
            fig_path = await self._create_channel_chart(data["channel_performance"])
            if fig_path:
                img = Image(str(fig_path), width=5 * inch, height=3 * inch)
                story.append(img)
                story.append(Spacer(1, 0.2 * inch))

            # Table
            headers = ["Channel", "Sent", "Delivered", "Failed", "Success Rate"]
            table_data = [headers]
            for channel in data["channel_performance"]:
                table_data.append(
                    [
                        channel.get("channel", ""),
                        channel.get("sent", 0),
                        channel.get("delivered", 0),
                        channel.get("failed", 0),
                        f"{channel.get('success_rate', 0):.1%}",
                    ]
                )

            channel_table = Table(table_data, colWidths=[1.5 * inch] * 5)
            channel_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, 0), 10),
                        ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                        ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                        ("GRID", (0, 0), (-1, -1), 1, colors.black),
                    ]
                )
            )
            story.append(channel_table)
            story.append(PageBreak())

        # Daily activity
        if data.get("daily_breakdown"):
            story.append(Paragraph("Daily Activity", heading_style))

            # Create visualization
            fig_path = await self._create_daily_chart(data["daily_breakdown"])
            if fig_path:
                img = Image(str(fig_path), width=6 * inch, height=4 * inch)
                story.append(img)
                story.append(Spacer(1, 0.2 * inch))

        # Insights
        if data.get("insights"):
            story.append(Paragraph("Insights", heading_style))
            for insight in data["insights"]:
                story.append(Paragraph(f"• {insight}", normal_style))
            story.append(Spacer(1, 0.2 * inch))

        # Build PDF
        doc.build(story)

        return file_path, file_path.stat().st_size

    async def _generate_html_report(
        self,
        report_id: str,
        data: dict[str, Any],
        template_name: str,
    ) -> tuple[Path, int]:
        """Generate HTML report file."""
        file_path = self.reports_dir / f"{report_id}.html"

        # Use Jinja2 template if available
        try:
            template = self.jinja_env.get_template(f"{template_name}.html")
            html_content = template.render(data=data, report_id=report_id)
        except Exception:
            # Fallback to basic HTML
            html_content = self._generate_basic_html(data)

        file_path.write_text(html_content)

        return file_path, len(html_content)

    def _generate_basic_html(self, data: dict[str, Any]) -> str:
        """Generate basic HTML report."""
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>{data.get("report_type", "Report")}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
        .summary {{ background-color: #f9f9f9; padding: 15px; margin: 20px 0; }}
        .insight {{ margin: 10px 0; padding: 10px; background-color: #e7f3ff; }}
    </style>
</head>
<body>
    <h1>{data.get("report_type", "Report").replace("_", " ").title()}</h1>
"""

        # Add period
        if "period" in data:
            html += f"<p>Period: {data['period']['start']} to {data['period']['end']}</p>"

        # Add summary
        if "summary" in data:
            html += "<div class='summary'><h2>Summary</h2>"
            for key, value in data["summary"].items():
                html += f"<p><strong>{key.replace('_', ' ').title()}:</strong> {value}</p>"
            html += "</div>"

        # Add channel performance
        if data.get("channel_performance"):
            html += "<h2>Channel Performance</h2><table>"
            html += "<tr><th>Channel</th><th>Sent</th><th>Delivered</th><th>Failed</th><th>Success Rate</th></tr>"
            for channel in data["channel_performance"]:
                html += f"""
                <tr>
                    <td>{channel.get("channel", "")}</td>
                    <td>{channel.get("sent", 0)}</td>
                    <td>{channel.get("delivered", 0)}</td>
                    <td>{channel.get("failed", 0)}</td>
                    <td>{channel.get("success_rate", 0):.1%}</td>
                </tr>
                """
            html += "</table>"

        # Add insights
        if data.get("insights"):
            html += "<h2>Insights</h2>"
            for insight in data["insights"]:
                html += f"<div class='insight'>{insight}</div>"

        html += "</body></html>"
        return html

    async def _create_channel_chart(self, channel_data: list[dict]) -> Path | None:
        """Create channel performance chart."""
        try:
            channels = [ch["channel"] for ch in channel_data]
            success_rates = [ch["success_rate"] for ch in channel_data]

            plt.figure(figsize=(8, 6))
            bars = plt.bar(channels, success_rates)

            # Color bars based on performance
            for i, bar in enumerate(bars):
                if success_rates[i] >= 0.95:
                    bar.set_color("green")
                elif success_rates[i] >= 0.8:
                    bar.set_color("orange")
                else:
                    bar.set_color("red")

            plt.ylabel("Success Rate")
            plt.title("Channel Performance")
            plt.ylim(0, 1.1)

            # Add value labels
            for i, v in enumerate(success_rates):
                plt.text(i, v + 0.01, f"{v:.1%}", ha="center")

            plt.tight_layout()

            # Save chart
            chart_path = self.reports_dir / f"channel_chart_{uuid4()}.png"
            plt.savefig(chart_path, dpi=150)
            plt.close()

            return chart_path

        except Exception as e:
            self.logger.error(f"Failed to create channel chart: {e}")
            return None

    async def _create_daily_chart(self, daily_data: list[dict]) -> Path | None:
        """Create daily activity chart."""
        try:
            dates = [d["date"] for d in daily_data]
            counts = [d["count"] for d in daily_data]

            plt.figure(figsize=(10, 6))
            plt.plot(dates, counts, marker="o", linewidth=2, markersize=8)

            plt.xlabel("Date")
            plt.ylabel("Notification Count")
            plt.title("Daily Notification Activity")
            plt.xticks(rotation=45)
            plt.grid(True, alpha=0.3)

            plt.tight_layout()

            # Save chart
            chart_path = self.reports_dir / f"daily_chart_{uuid4()}.png"
            plt.savefig(chart_path, dpi=150)
            plt.close()

            return chart_path

        except Exception as e:
            self.logger.error(f"Failed to create daily chart: {e}")
            return None

    # Scheduler methods

    async def _scheduler_loop(self) -> None:
        """Background loop for scheduled reports."""
        while self._running:
            try:
                now = datetime.now(UTC)

                for schedule_id, config in self._scheduled_reports.items():
                    if config["next_run"] and now >= config["next_run"]:
                        await self._run_scheduled_report(schedule_id, config)

                # Check every minute
                await asyncio.sleep(60)

            except Exception as e:
                self.logger.error(f"Scheduler error: {e}")

    async def _run_scheduled_report(
        self,
        schedule_id: str,
        config: dict[str, Any],
    ) -> None:
        """Run a scheduled report."""
        try:
            # Determine report period based on template
            template_name = config["template"]
            now = datetime.now(UTC)

            if template_name == "daily_digest":
                start_date = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
                    days=1
                )
                end_date = start_date + timedelta(days=1)
            elif template_name == "weekly_analytics":
                start_date = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
                    days=7
                )
                end_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                # Default to last 24 hours
                start_date = now - timedelta(days=1)
                end_date = now

            # Generate report
            report = await self.generate_report(
                template_name=template_name,
                start_date=start_date,
                end_date=end_date,
                format=config["format"],
                parameters=config["parameters"],
                generated_by=f"Scheduled ({schedule_id})",
            )

            # Update schedule
            config["last_run"] = now
            config["next_run"] = self._calculate_next_run(config["schedule"])

            # Send to recipients if configured
            if config["recipients"]:
                await self._send_report_to_recipients(report, config["recipients"])

            self.logger.info(f"Generated scheduled report {report.report_id}")

        except Exception as e:
            self.logger.error(f"Failed to run scheduled report {schedule_id}: {e}")

    def _calculate_next_run(self, schedule: dict[str, Any]) -> datetime:
        """Calculate next run time for schedule."""
        now = datetime.now(UTC)

        if "interval" in schedule:
            # Simple interval-based scheduling
            interval = schedule["interval"]
            if interval == "daily":
                return now.replace(hour=schedule.get("hour", 0), minute=0, second=0) + timedelta(
                    days=1
                )
            if interval == "weekly":
                days_ahead = schedule.get("day_of_week", 0) - now.weekday()
                if days_ahead <= 0:
                    days_ahead += 7
                return now.replace(hour=schedule.get("hour", 0), minute=0, second=0) + timedelta(
                    days=days_ahead
                )
            if interval == "hourly":
                return now.replace(minute=0, second=0) + timedelta(hours=1)

        # Default to next day
        return now + timedelta(days=1)

    async def _send_report_to_recipients(
        self,
        report: NotificationReportModel,
        recipients: list[str],
    ) -> None:
        """Send report to email recipients."""
        # This would integrate with the notification system to send emails
        # For now, just log
        self.logger.info(f"Would send report {report.report_id} to {len(recipients)} recipients")
