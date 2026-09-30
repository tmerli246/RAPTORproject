"""Figures for the allocator.

Style follows what Physics in Medicine and Biology and Medical Physics expect.

Every figure takes a `synthetic` flag. When true a corner marker is drawn.

Input convention. The drawing functions take a list of result records, the
flat dicts of `report.sweep` and `report.sweep_budget_xt`, one per cohort and
point. A record may carry a 'cohort' key. Where several cohorts are present a
curve is the median over cohorts with the interquartile band; with one cohort
it is a plain line. Where the cohorts come from, generated seeds or anything
else, is not the concern of this module.
"""

import os
import textwrap

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.transforms import ScaledTranslation

from tps5d.allocator.dominance import pareto, hull

COLORS = {
    'P0': '#000000',
    'P1': '#E69F00',
    'P1x': '#D55E00',
    'P2a': '#56B4E9',
    'P2b': '#009E73',
    'P3': '#0072B2',
}
# P1 and P1x coincide whenever the photon budget is zero, and P2b lies close to
# P3, so the lines differ in style as well as in colour, and P3 is drawn wide and
# underneath.
LINESTYLES = {'P0': '--', 'P1': '-', 'P1x': (0, (4, 1.5, 1, 1.5)),
              'P2a': '-', 'P2b': (0, (1, 1.2)), 'P3': '-'}
LINEWIDTHS = {'P3': 2.6, 'P2b': 1.4}
ZORDERS = {'P3': 2, 'P2b': 4}

# Proton arms in blue, photon arms in orange; the non-adapted arm is the light
# shade, the adapted arm the dark one; a hatch marks the hypofractionated
# schedule. Keyed on report.arm_label, without the schedule suffix.
ARM_COLORS = {'PT-NA': '#9ECAE1', 'PT-A': '#2171B5',
              'XT-NA': '#FDD0A2', 'XT-A': '#E6550D'}
ARM_ORDER = ('PT-NA', 'PT-A', 'XT-NA', 'XT-A')

GREY = '#7F7F7F'
MM = 1.0 / 25.4
COL1, COL2 = 90 * MM, 180 * MM      # single and double column width

def use_style():
    """Apply the manuscript style. Call once before making figures."""
    mpl.rcParams.update({
        'figure.dpi': 120,
        'savefig.dpi': 600,
        'savefig.bbox': 'tight',
        'font.family': 'sans-serif',
        'font.size': 8,
        'axes.labelsize': 8,
        'axes.titlesize': 6,
        'axes.linewidth': 0.6,
        'axes.spines.top': False,
        'axes.spines.right': False,
        'xtick.labelsize': 7,
        'ytick.labelsize': 7,
        'xtick.major.width': 0.6,
        'ytick.major.width': 0.6,
        'legend.fontsize': 7,
        'legend.frameon': False,
        'lines.linewidth': 1.2,
        'lines.markersize': 3.5,
        'grid.linewidth': 0.4,
        'grid.color': '#DDDDDD',
    })

def _header(ax, note, synthetic):
    """Subtitle and synthetic marker.

    The note, wrapped to the axes width, sits above the axes at the left, and
    the marker above the note.
    """
    lines = 0
    if note:
        wrapped = textwrap.fill(note, 62)
        ax.set_title(wrapped, loc = 'left')
        lines = wrapped.count('\n') + 1
    if synthetic:
        ax.annotate('SYNTHETIC COHORT', (0.0, 1.0), xycoords = 'axes fraction',
                    xytext = (0, 4 + 7.5 * lines), textcoords = 'offset points',
                    ha = 'left', va = 'bottom', fontsize = 6, color = '#B03A2E',
                    fontweight = 'bold')

def _legend_below(ax, ncols):
    """Legend under the axes, clear of the tick labels and the x label."""
    below = ScaledTranslation(0, -34 / 72, ax.figure.dpi_scale_trans)
    ax.legend(loc = 'upper center', bbox_to_anchor = (0.5, 0),
              bbox_transform = ax.transAxes + below, ncols = ncols)

def _save(fig, path):
    """Write `path` and its twin: PDF and PNG, each once. A path without an
    extension is taken as a stem. The PDF carries no creation date, so that
    two runs give the same bytes."""
    if path:
        stem, ext = os.path.splitext(str(path))
        for e in dict.fromkeys([ext.lower() or '.pdf', '.pdf', '.png']):
            meta = {'CreationDate': None} if e == '.pdf' else None
            fig.savefig(stem + e, metadata = meta)
    return fig

def _curve(records, x, y, where = None):
    """Median and interquartile band of `y` over cohorts at each value of `x`.

    Records sharing a (cohort, x) are one observation, whatever else they
    carry, so a quantity that is the same across policies, such as a shadow
    price, is counted once per cohort. Returns (xs, median, q25, q75, n) with
    n the largest number of cohorts at any point.
    """
    obs = {}
    for r in records:
        if where is None or where(r):
            obs[(r.get('cohort', 0), r[x])] = r[y]
    groups = {}
    for (_, xv), yv in obs.items():
        groups.setdefault(xv, []).append(yv)
    xs = np.array(sorted(groups))
    ys = [np.asarray(groups[v], dtype = float) for v in xs]
    med = np.array([np.median(a) for a in ys])
    q25 = np.array([np.percentile(a, 25) for a in ys])
    q75 = np.array([np.percentile(a, 75) for a in ys])
    return xs, med, q25, q75, max(len(a) for a in ys)

def _draw(ax, xs, med, q25, q75, n, color, scale = 1.0, band = True, **kw):
    """One curve with its band, where there is more than one cohort."""
    ax.plot(xs, scale * med, color = color, **kw)
    if n > 1 and band:
        ax.fill_between(xs, scale * q25, scale * q75, color = color,
                        alpha = 0.15, linewidth = 0, step = kw.get('drawstyle', '')[6:] or None)

def _cohort_note(records, extra = '', stat = 'median and interquartile range'):
    """Number of cohorts behind the curves, for the subtitle."""
    n = len({r.get('cohort', 0) for r in records})
    head = f"{stat} over {n} cohorts" if n > 1 else "one cohort"
    return head + (f"; {extra}" if extra else '')

def policy_curves(records, path = None, synthetic = True, policies = None, note = ''):
    """Cohort delta NTCP against adaptation time, one line per policy.

    The reference study's central figure, generalised: there the lines were
    margin arms under one allocation rule, here they are allocation rules. P0
    is drawn as a dashed reference, since it is current practice and the
    question is which policies sit above it.

    policies restricts the lines drawn. At a zero photon budget P1x is P1, and
    the caller decides whether to draw both.
    """
    fig, ax = plt.subplots(figsize = (COL1, 66 * MM))
    pols = sorted({r['policy'] for r in records} & set(policies or COLORS),
                  key = lambda p: list(COLORS).index(p))

    for p in pols:
        xs, med, lo, hi, n = _curve(records, 'dtau', 'mean_dntcp',
                                    lambda r, p = p: r['policy'] == p)
        _draw(ax, xs, med, lo, hi, n, COLORS[p], scale = 100.0, ls = LINESTYLES[p],
              lw = LINEWIDTHS.get(p), zorder = ZORDERS.get(p, 3),
              marker = None if p == 'P0' else 'o',
              label = 'P0, current practice' if p == 'P0' else p)

    ax.set_xlabel(r'extra time per adapted fraction, $\Delta\tau_{PT}$  (min)')
    ax.set_ylabel(r'cohort mean $\Delta$NTCP  (%)')
    ax.grid(axis = 'y')
    _legend_below(ax, ncols = 3)
    _header(ax, _cohort_note(records, note), synthetic)
    fig.tight_layout()
    return _save(fig, path)

def shadow_price(records, path = None, synthetic = True, note = ''):
    """The proton shadow price against adaptation time.

    Lambda is the cohort delta NTCP bought by one additional machine-minute,
    summed over patients, that is the expected number of avoided complications
    per machine-minute. A workflow change costing an extra delta tau per
    fraction is worthwhile for a patient exactly when the utility it buys
    exceeds lambda times that time, so this curve is the exchange rate behind
    the reference study's threshold.
    """
    fig, ax = plt.subplots(figsize = (COL1, 58 * MM))
    xs, med, lo, hi, n = _curve(records, 'dtau', 'lambda_pt')
    _draw(ax, xs, med, lo, hi, n, COLORS['P3'], scale = 100.0, marker = 'o')
    ax.set_xlabel(r'extra time per adapted fraction, $\Delta\tau_{PT}$  (min)')
    ax.set_ylabel(r'$\lambda_{PT}$  (avoided complications' '\n' r'per 100 machine-min)')
    ax.grid(axis = 'y')
    _header(ax, _cohort_note(records, note), synthetic)
    fig.tight_layout()
    return _save(fig, path)

def _arm_style(label):
    """Colour and hatch of an arm label as report.arm_label writes it."""
    stem, _, scheme = label.partition(' ')
    return ARM_COLORS.get(stem, GREY), ('///' if scheme else None)

def cohort_composition(records, policy = 'P3', path = None, synthetic = True, note = ''):
    """Who receives what, as a function of adaptation time.

    The quantitative form of the reference study's patient icons: as adaptation
    lengthens, patients are displaced from protons to photons. With both
    schedules the intermediate categories can also be occupied, and whether
    they are is the question the allocator exists to answer. Bars are the mean
    number of patients per arm over the cohorts present.
    """
    rs = [r for r in records if r['policy'] == policy]
    dtaus = sorted({r['dtau'] for r in rs})
    labels = {k[2:] for r in rs for k in r if k[2:4] in ('PT', 'XT') and k.startswith('n_')}
    rank = lambda l: (ARM_ORDER.index(l.split(' ')[0]) if l.split(' ')[0] in ARM_ORDER
                      else len(ARM_ORDER), ' ' in l, l)
    order = sorted(labels, key = rank)

    fig, ax = plt.subplots(figsize = (COL1, 62 * MM))
    x = np.arange(len(dtaus))
    bottom = np.zeros(len(dtaus))
    for lab in order:
        vals = np.array([np.mean([r.get(f'n_{lab}', 0) for r in rs if r['dtau'] == d])
                         for d in dtaus])
        col, hatch = _arm_style(lab)
        ax.bar(x, vals, bottom = bottom, color = col, width = 0.72, hatch = hatch,
               edgecolor = 'white', linewidth = 0.4, label = lab)
        bottom += vals

    ax.set_xticks(x, [f"{d:g}" for d in dtaus])
    ax.set_xlabel(r'$\Delta\tau_{PT}$  (min)')
    ax.set_ylabel('patients')
    _legend_below(ax, ncols = 4)
    _header(ax, _cohort_note(rs, f'{policy}' + (f'; {note}' if note else ''), stat = 'mean'),
            synthetic)
    fig.tight_layout()
    return _save(fig, path)

def option_ladder(cohort, pid, path = None, synthetic = True, note = ''):
    """One patient's option set, with the two reductions drawn.

    A methods figure rather than a result, and one named patient by
    construction. It shows why ranking whole strategies by benefit density is
    the wrong statistic: every patient already holds the photon option at zero
    proton cost, so the decision is which rung to climb to, and the slopes
    between consecutive surviving options are what the allocation compares
    across patients.
    """
    # The proton chain: the ladder lives on the proton cost axis, and the
    # photon-adapted options belong to the other chain.
    opts = [s for s in cohort.by_patient()[pid] if s.tau_xt == 0.0]
    pts = [(s.occ_pt, 100 * cohort.dntcp(s)) for s in opts]
    i_par, i_hull = pareto(pts), hull(pts)

    fig, ax = plt.subplots(figsize = (COL1, 62 * MM))

    dominated = [i for i in range(len(pts)) if i not in i_par]
    lp_only = [i for i in i_par if i not in i_hull]

    if dominated:
        ax.scatter([pts[i][0] for i in dominated], [pts[i][1] for i in dominated],
                   marker = 'x', color = GREY, label = 'Pareto dominated', zorder = 3)
    if lp_only:
        ax.scatter([pts[i][0] for i in lp_only], [pts[i][1] for i in lp_only],
                   facecolors = 'none', edgecolors = COLORS['P1'],
                   label = 'LP dominated', zorder = 3)

    hx = [pts[i][0] for i in i_hull]
    hy = [pts[i][1] for i in i_hull]
    ax.plot(hx, hy, color = COLORS['P3'], marker = 'o', zorder = 4,
            label = 'upper hull, selectable')

    origin = min(range(len(pts)), key = lambda i: pts[i][0])
    for i, (x, y) in enumerate(pts):
        on_hull = i in i_hull
        # the free arm sits on the axis: its label goes above it
        ax.annotate(opts[i].sid, (x, y), textcoords = 'offset points',
                    xytext = (6, 5) if i == origin else (5, -9), fontsize = 6,
                    color = COLORS['P3'] if on_hull else GREY)

    # Incremental efficiency is the slope of each hull segment, and it is what
    # the allocation ranks across patients. The label sits below the segment,
    # away from the option labels above and to its right.
    for a, b in zip(i_hull, i_hull[1:]):
        dx = pts[b][0] - pts[a][0]
        dy = pts[b][1] - pts[a][1]
        ax.annotate(f"{dy / dx:.4f} %/min",
                    (0.5 * (pts[a][0] + pts[b][0]), 0.5 * (pts[a][1] + pts[b][1])),
                    textcoords = 'offset points', xytext = (6, -12), fontsize = 6,
                    ha = 'left', color = GREY)

    ax.set_xlabel('course occupancy  (machine-min)')
    ax.set_ylabel(r'$\Delta$NTCP against baseline  (%)')
    ax.grid(axis = 'y')
    _legend_below(ax, ncols = 3)
    _header(ax, f'patient {pid}' + (f'; {note}' if note else ''), synthetic)
    fig.tight_layout()
    return _save(fig, path)

def budget_curves(records, path = None, synthetic = True, note = ''):
    """The two shadow prices along the normalised photon budget axis.

    lambda_xt is reported as a curve because the budget has no measured anchor
    (allocator design, Section 5.2); its endpoints are the reference study's
    comparator and the free case. Where the ratio lambda_xt / lambda_pt
    exceeds one, the next minute of photon adaptation capability buys more
    cohort benefit than the next proton minute. The shadow prices of a linear
    programme are piecewise constant in the budget, so the curves are drawn as
    steps, each value holding until the next grid point.
    """
    fig, ax = plt.subplots(figsize = (COL1, 62 * MM))
    for key, col, mk, lab in (('lambda_pt', COLORS['P3'], 'o', r'$\lambda_{PT}$'),
                              ('lambda_xt', COLORS['P1x'], 's', r'$\lambda_{XT}$')):
        xs, med, lo, hi, n = _curve(records, 'cxt_frac', key)
        _draw(ax, xs, med, lo, hi, n, col, scale = 100.0, marker = mk, label = lab,
              drawstyle = 'steps-post')
    ax.set_xlabel(r'photon adaptation budget  (fraction of cohort demand, $C_{XT}/D_{XT}$)')
    ax.set_ylabel(r'$\lambda$  (avoided complications' '\n' r'per 100 machine-min)')
    ax.grid(axis = 'y')
    ax.legend(loc = 'best')
    _header(ax, _cohort_note(records, note), synthetic)
    fig.tight_layout()
    return _save(fig, path)

def _course_label(v):
    """1/6, 1/3, 1/2 as fractions, everything else as a plain number."""
    for num, den in ((1, 6), (1, 3), (1, 2)):
        if abs(v - num / den) < 1e-9:
            return f'{num}/{den}'
    return f'{v:g}'

def policy_budget(records, course_min, path = None, synthetic = True,
                  policies = None, note = ''):
    """Cohort delta NTCP of each policy against the photon adaptation budget.

    The budget is measured in standard courses, `course_min` machine-minutes
    each (one patient's standard-schedule adapted photon course,
    n_fx,std x delta tau_XT). A hypofractionated course is a sixth of one
    at the generator's fraction counts. The axis is linear up to one sixth of
    a course and logarithmic beyond, since most of what the budget buys is
    bought early; points sit on the grid the caller swept.
    """
    fig, ax = plt.subplots(figsize = (COL1, 66 * MM))
    pols = sorted({r['policy'] for r in records} & set(policies or COLORS),
                  key = lambda p: list(COLORS).index(p))
    grid = set()
    rs = [dict(r, courses = r['cxt_min'] / course_min) for r in records]
    for p in pols:
        xs, med, lo, hi, n = _curve(rs, 'courses', 'mean_dntcp',
                                    lambda r, p = p: r['policy'] == p)
        grid |= set(np.round(xs, 9))
        _draw(ax, xs, med, lo, hi, n, COLORS[p], scale = 100.0, ls = LINESTYLES[p],
              lw = LINEWIDTHS.get(p), zorder = ZORDERS.get(p, 3),
              marker = None if p == 'P0' else 'o',
              label = 'P0, current practice' if p == 'P0' else p)

    ticks = sorted(grid)
    ax.set_xscale('symlog', linthresh = 1 / 6, linscale = 0.6)
    ax.set_xticks(ticks, [_course_label(v) for v in ticks])
    ax.minorticks_off()
    ax.set_xlabel(r'photon adaptation budget, $C_{XT}$  (standard courses)')
    ax.set_ylabel(r'cohort mean $\Delta$NTCP  (%)')
    ax.grid(axis = 'y')
    _legend_below(ax, ncols = 3)
    _header(ax, _cohort_note(records, note), synthetic)
    fig.tight_layout()
    return _save(fig, path)
