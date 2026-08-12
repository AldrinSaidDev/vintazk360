/* Shared "Actual vs Target" chart for the LOB dashboards.
 *
 * Reads its data from a <script type="application/json" id="kpi-chart-data">
 * block (Django's json_script) and draws into <canvas id="kpiChart">. Both are
 * emitted by templates/kpi/dashboard.html — this file makes no assumptions
 * beyond those two ids, so any LOB gets the same chart for free.
 *
 * Row shape: {name, attainment, status, actual_display, target_display}.
 * KPIs without a target are filtered out server-side; there is nothing to plot
 * against, so an empty payload simply draws nothing.
 */
(function () {
    const el = document.getElementById('kpiChart');
    const dataEl = document.getElementById('kpi-chart-data');
    if (!el || !dataEl || typeof Chart === 'undefined') return;

    const rows = JSON.parse(dataEl.textContent);
    if (!rows.length) return;

    // Brand-anchored semantic status colors. On-track reuses the brand purple
    // (stays on-brand); at-risk / below are muted amber / rose so problem
    // states read clearly without looking loud.
    const COLORS = {
        on_track: '#4F3D67',  // brand purple — on track
        at_risk:  '#D9A441',  // muted amber — at risk
        below:    '#C25B6E',  // muted rose  — below target
    };
    const FONT = "'Space Grotesk', ui-sans-serif, system-ui, sans-serif";

    const labels = rows.map(r => r.name);
    const values = rows.map(r => r.attainment);
    const colors = rows.map(r => COLORS[r.status] || '#94a3b8');

    new Chart(el, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: '% of target',
                data: values,
                backgroundColor: colors,
                hoverBackgroundColor: colors,
                borderRadius: 5,
                borderSkipped: false,
                barThickness: 18,
                maxBarThickness: 22,
            }],
        },
        options: {
            indexAxis: 'y',              // horizontal bars — long KPI names read better
            responsive: true,
            maintainAspectRatio: false,
            layout: { padding: { right: 44, top: 8, bottom: 4 } },  // room for value labels
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#040404',
                    padding: 12,
                    cornerRadius: 8,
                    titleFont: { family: FONT, weight: '700', size: 12 },
                    bodyFont: { family: FONT, size: 12 },
                    bodySpacing: 4,
                    displayColors: false,
                    callbacks: {
                        title: ctx => rows[ctx[0].dataIndex].name,
                        label: function (ctx) {
                            const r = rows[ctx.dataIndex];
                            return [
                                `${r.attainment}% of target`,
                                `Actual ${r.actual_display}  ·  Target ${r.target_display}`,
                            ];
                        },
                    },
                },
            },
            scales: {
                x: {
                    beginAtZero: true,
                    suggestedMax: 120,
                    border: { display: false },
                    ticks: {
                        callback: v => v + '%',
                        color: '#94a3b8',
                        font: { family: FONT, size: 11 },
                        padding: 6,
                    },
                    grid: { color: '#f1f5f9', drawTicks: false },
                },
                y: {
                    border: { display: false },
                    ticks: {
                        color: '#334155',
                        font: { family: FONT, weight: '600', size: 12 },
                        padding: 8,
                    },
                    grid: { display: false },
                },
            },
        },
        plugins: [
            {
                // Dashed "100% = target" reference line across the plot.
                id: 'targetLine',
                beforeDatasetsDraw(chart) {
                    const { ctx, chartArea: area, scales } = chart;
                    const x = scales.x.getPixelForValue(100);
                    if (x < area.left || x > area.right) return;
                    ctx.save();
                    ctx.strokeStyle = '#94a3b8';
                    ctx.lineWidth = 1.5;
                    ctx.setLineDash([4, 4]);
                    ctx.beginPath();
                    ctx.moveTo(x, area.top - 4);
                    ctx.lineTo(x, area.bottom);
                    ctx.stroke();
                    ctx.setLineDash([]);
                    ctx.fillStyle = '#64748b';
                    ctx.font = `600 10px ${FONT}`;
                    ctx.textAlign = 'center';
                    ctx.fillText('TARGET', x, area.top - 8);
                    ctx.restore();
                },
            },
            {
                // Value label (attainment %) at the end of each bar.
                id: 'valueLabels',
                afterDatasetsDraw(chart) {
                    const { ctx } = chart;
                    const meta = chart.getDatasetMeta(0);
                    ctx.save();
                    ctx.font = `700 11px ${FONT}`;
                    ctx.textBaseline = 'middle';
                    ctx.textAlign = 'left';
                    meta.data.forEach((bar, i) => {
                        ctx.fillStyle = colors[i];
                        ctx.fillText(`${values[i]}%`, bar.x + 8, bar.y);
                    });
                    ctx.restore();
                },
            },
        ],
    });
})();
