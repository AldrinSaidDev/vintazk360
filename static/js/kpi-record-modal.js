/* Shared Add-Performance-Record modal calculator (templates/kpi/import_data.html).
 *
 * Pick a KPI → the two inputs relabel to that KPI's formula parts → the panel
 * shows the worked calculation, then band-aware attainment vs target and a
 * status pill. All client-side; nothing is persisted (Save is a mockup).
 *
 * Every KPI carries a `kind` telling this script how to combine the two raw
 * figures and how to word the result:
 *
 *   percent     a ÷ b × 100          most rate KPIs
 *   count       a                    a single tally; the second field is hidden
 *   average     a ÷ b                days-to-fill, satisfaction ratings (unit suffix)
 *   ratio       a ÷ b                reads as "3.4×"
 *   cost        a ÷ b                reads as "₱1,180"
 *   difference  a − b                eNPS, hours saved
 *   days        date a − date b      turnaround in whole days
 *   net_percent (a − b) ÷ a × 100    accuracy net of errors (a = total, b = errors)
 *   variance    (a − b) ÷ b × 100    signed budget variance, SCORED on |value|
 *   accuracy    (1 − |a−b| ÷ b) × 100  forecast vs actual
 *   scaled      (a ÷ b) × c          the only kind with a third input (DSO)
 *
 * evaluate() may return a `score` distinct from `value` — used where the number
 * shown and the number graded differ (a −3.2% budget variance displays signed
 * but is graded on 3.2 against a ±5 tolerance).
 *
 * Tailwind note: the status pill classes below are built as strings, so
 * ./static/js is in the Tailwind content globs — otherwise they'd be purged.
 */
(function () {
    const kpiSel   = document.getElementById('record-kpi');
    const inputs   = document.getElementById('record-inputs');
    const bField   = document.getElementById('record-b-field');
    const cField   = document.getElementById('record-c-field');
    const aEl      = document.getElementById('record-a');
    const bEl      = document.getElementById('record-b');
    const cEl      = document.getElementById('record-c');
    const aLabel   = document.getElementById('record-a-label');
    const bLabel   = document.getElementById('record-b-label');
    const cLabel   = document.getElementById('record-c-label');
    const panel    = document.getElementById('record-calc');
    const fEl      = document.getElementById('record-calc-formula');
    const workedEl = document.getElementById('record-calc-worked');
    const tEl      = document.getElementById('record-calc-target');
    const sEl      = document.getElementById('record-calc-status');
    const hintEl   = document.getElementById('record-calc-hint');
    if (!kpiSel || !inputs || !panel) return;

    // Mirrors the dashboard's semantic status colors.
    const STATUS = {
        on_track:  { label: 'On Track',     cls: 'bg-status-good/10 text-status-good' },
        at_risk:   { label: 'At Risk',      cls: 'bg-status-warn/15 text-status-warn' },
        below:     { label: 'Below Target', cls: 'bg-status-bad/10 text-status-bad' },
        monitored: { label: 'No Target',    cls: 'bg-slate-100 text-slate-500' },
    };

    const DAY_MS = 86400000;

    // Trim trailing zeros so "58.00" reads as "58".
    const fmt = n => Number(n.toFixed(2)).toString();
    const money = n => '₱' + Number(n.toFixed(2)).toLocaleString('en-PH');
    const num = el => {
        const v = parseFloat((el.value || '').replace(/[^0-9.\-]/g, ''));
        return isNaN(v) ? null : v;
    };
    const date = el => {
        const t = Date.parse(el.value);   // yyyy-mm-dd parses as UTC midnight
        return isNaN(t) ? null : t;
    };
    // Empty data-min / data-max means the KPI has no target to score against.
    const bound = raw => (raw === '' ? null : parseFloat(raw));

    function evaluate(kind, unit) {
        if (kind === 'days') {
            const ready = date(aEl), zero = date(bEl);
            if (ready === null || zero === null) return null;
            const value = Math.round((ready - zero) / DAY_MS);
            return { value: value, worked: `${aEl.value} − ${bEl.value} = ${value} day${value === 1 ? '' : 's'}` };
        }

        const a = num(aEl);
        if (a === null) return null;

        if (kind === 'count') {
            return { value: a, worked: `${fmt(a)}${unit ? ' ' + unit : ''} recorded this period` };
        }

        const b = num(bEl);
        if (b === null) return null;

        if (kind === 'difference') {
            const value = a - b;
            return { value: value, worked: `${fmt(a)} − ${fmt(b)} = ${fmt(value)}${unit}` };
        }

        if (kind === 'net_percent') {   // a = total, b = errors
            if (a === 0) return null;
            const value = (a - b) / a * 100;
            return { value: value, worked: `(${fmt(a)} − ${fmt(b)}) ÷ ${fmt(a)} × 100 = ${fmt(value)}%` };
        }

        if (b === 0) return null;   // divisor KPIs need a non-zero denominator

        if (kind === 'variance') {     // signed variance, graded on its magnitude
            const value = (a - b) / b * 100;
            const sign = value > 0 ? '+' : '';
            return {
                value: value,
                score: Math.abs(value),
                worked: `(${fmt(a)} − ${fmt(b)}) ÷ ${fmt(b)} × 100 = ${sign}${fmt(value)}%`,
            };
        }

        if (kind === 'accuracy') {     // a = forecast, b = actual
            const value = (1 - Math.abs(a - b) / b) * 100;
            return { value: value, worked: `(1 − |${fmt(a)} − ${fmt(b)}| ÷ ${fmt(b)}) × 100 = ${fmt(value)}%` };
        }

        if (kind === 'scaled') {       // (a ÷ b) × c — e.g. DSO over a period
            const c = num(cEl);
            if (c === null) return null;
            const value = a / b * c;
            return { value: value, worked: `(${fmt(a)} ÷ ${fmt(b)}) × ${fmt(c)} = ${fmt(value)}${unit}` };
        }

        if (kind === 'cost') {
            const value = a / b;
            return { value: value, worked: `${fmt(a)} ÷ ${fmt(b)} = ${money(value)}` };
        }
        if (kind === 'ratio') {
            const value = a / b;
            return { value: value, worked: `${fmt(a)} ÷ ${fmt(b)} = ${fmt(value)}×` };
        }
        if (kind === 'average') {
            const value = a / b;
            return { value: value, worked: `${fmt(a)} ÷ ${fmt(b)} = ${fmt(value)}${unit}` };
        }
        const value = a / b * 100;    // percent
        return { value: value, worked: `${fmt(a)} ÷ ${fmt(b)} × 100 = ${fmt(value)}%` };
    }

    // Band-aware attainment — matches apps/core/kpi.attainment(). Inside the
    // target band is 100%; outside it, measured against the edge missed.
    function attainment(value, low, high, direction) {
        if (low === null || high === null) return null;
        if (direction === 'down') {
            if (high === 0) return value === 0 ? 100 : 0;
            if (!value) return 100;
            if (value > high) return high / value * 100;
            if (value < low) return low / value * 100;
            return 100;
        }
        if (!value) return 0;
        if (value < low) return value / low * 100;
        if (value > high) return value / high * 100;
        return 100;
    }

    function render() {
        const opt = kpiSel.selectedOptions[0];

        if (!opt || !opt.value) {          // no KPI chosen
            inputs.classList.add('hidden');
            panel.classList.add('hidden');
            return;
        }

        const kind = opt.dataset.kind;

        // Relabel/retype the inputs to this KPI's formula parts, reveal them.
        aLabel.textContent = opt.dataset.aLabel;
        bLabel.textContent = opt.dataset.bLabel;
        cLabel.textContent = opt.dataset.cLabel || '';
        aEl.placeholder = opt.dataset.aPh || '';
        bEl.placeholder = opt.dataset.bPh || '';
        cEl.placeholder = opt.dataset.cPh || '';
        aEl.type = bEl.type = kind === 'days' ? 'date' : 'text';
        bField.classList.toggle('hidden', kind === 'count');
        // Only the 'scaled' kind declares a third figure.
        cField.classList.toggle('hidden', !opt.dataset.cLabel);
        inputs.classList.remove('hidden');

        panel.classList.remove('hidden');
        fEl.textContent = opt.dataset.formula;
        tEl.textContent = opt.dataset.targetDisplay;

        const result = evaluate(kind, opt.dataset.unit || '');
        if (!result) {
            workedEl.classList.add('hidden');
            sEl.classList.add('hidden'); sEl.classList.remove('inline-flex');
            hintEl.classList.remove('hidden');
            return;
        }

        // `score` differs from `value` where the number shown isn't the number
        // graded (a signed variance is graded on its magnitude).
        const graded = result.score === undefined ? result.value : result.score;
        const pct = attainment(graded, bound(opt.dataset.min), bound(opt.dataset.max), opt.dataset.direction);
        const key = pct === null ? 'monitored'
                  : (pct >= 100 ? 'on_track' : (pct >= 90 ? 'at_risk' : 'below'));
        const s = STATUS[key];

        workedEl.textContent = result.worked;
        workedEl.classList.remove('hidden');
        hintEl.classList.add('hidden');
        sEl.textContent = s.label;
        sEl.className = 'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold ' + s.cls;
    }

    kpiSel.addEventListener('change', render);
    [aEl, bEl, cEl].forEach(el => el.addEventListener('input', render));
})();
