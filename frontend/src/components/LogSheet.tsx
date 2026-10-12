import { useRef } from 'react'
import { fmtHour, fmtHours, splitDate } from '../format'
import type { DailyLog, DutyStatus } from '../types'

/**
 * SVG recreation of the paper "Driver's Daily Log (24 hours)" from the FMCSA
 * guide: header fields, 24-hour graph grid, remarks, shipping documents and the
 * 70-hour/8-day recap. Everything is drawn with plain SVG attributes (no CSS
 * classes) so the sheet can be exported to PNG.
 */

const W = 900
const GRID_X = 135
const GRID_W = 640
const HOUR_W = GRID_W / 24
const ROW_H = 34
const GRID_Y = 292
const ROWS: { status: DutyStatus; label: string[] }[] = [
  { status: 'off_duty', label: ['1. Off Duty'] },
  { status: 'sleeper', label: ['2. Sleeper', 'Berth'] },
  { status: 'driving', label: ['3. Driving'] },
  { status: 'on_duty', label: ['4. On Duty', '(not driving)'] },
]
const INK = '#111827'
const LINE = '#1d4ed8'
const FONT = 'Helvetica, Arial, sans-serif'

// What the driver was doing, in the short words used on a paper log's remarks
const FLAG_ACTIVITY: Record<string, string> = {
  drive: 'Driving',
  pickup: 'Pickup / loading',
  dropoff: 'Drop-off / unloading',
  fuel: 'Fueling',
  break: '30-min break',
  rest: '10-hr rest (sleeper)',
  restart: '34-hr restart',
  off: 'Off duty',
}

/** 510 -> "8:30" */
const fmtHM = (minutes: number) =>
  `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, '0')}`

const x = (hour: number) => GRID_X + hour * HOUR_W
const rowCenter = (i: number) => GRID_Y + i * ROW_H + ROW_H / 2
const rowIndex = (s: DutyStatus) => ROWS.findIndex((r) => r.status === s)

interface TextProps {
  x: number
  y: number
  size?: number
  weight?: number | string
  anchor?: 'start' | 'middle' | 'end'
  fill?: string
  children: React.ReactNode
  transform?: string
}

function T({ x, y, size = 11, weight = 400, anchor = 'start', fill = INK, children, transform }: TextProps) {
  return (
    <text
      x={x}
      y={y}
      fontSize={size}
      fontWeight={weight}
      textAnchor={anchor}
      fill={fill}
      fontFamily={FONT}
      transform={transform}
    >
      {children}
    </text>
  )
}

/** Underlined field with the value written above the line and a caption below. */
function Field({
  x: fx,
  y,
  width,
  value,
  caption,
  align = 'start',
}: {
  x: number
  y: number
  width: number
  value?: string
  caption?: string
  align?: 'start' | 'middle'
}) {
  const tx = align === 'middle' ? fx + width / 2 : fx + 4
  return (
    <g>
      {value ? (
        <T x={tx} y={y - 4} size={12} weight={600} anchor={align} fill="#1e3a8a">
          {value}
        </T>
      ) : null}
      <line x1={fx} x2={fx + width} y1={y} y2={y} stroke={INK} strokeWidth={0.9} />
      {caption ? (
        <T x={fx + width / 2} y={y + 12} size={9} anchor="middle">
          {caption}
        </T>
      ) : null}
    </g>
  )
}

function clip(text: string, max: number) {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text
}

export default function LogSheet({ log }: { log: DailyLog }) {
  const svgRef = useRef<SVGSVGElement>(null)
  const { year, month, day } = splitDate(log.date)

  // ---- layout that depends on the amount of remarks ----------------------
  const gridBottom = GRID_Y + ROWS.length * ROW_H
  const remarksTop = gridBottom + 34
  const remarksH = 150
  const shippingY = remarksTop + remarksH + 30
  const signatureY = shippingY + 62
  const tableTop = signatureY + 46
  const rowGap = 16
  const tableBottom = tableTop + 22 + log.remarks.length * rowGap
  const recapTop = tableBottom + 22
  const H = recapTop + 150

  // ---- row totals in hours:minutes ----------------------------------------
  // Boundaries (not durations) are rounded, so the four rows always add to 24:00.
  const minutes: Record<DutyStatus, number> = { off_duty: 0, sleeper: 0, driving: 0, on_duty: 0 }
  for (const seg of log.segments) {
    minutes[seg.status] += Math.round(seg.end * 60) - Math.round(seg.start * 60)
  }
  const totalMinutes = Object.values(minutes).reduce((a, b) => a + b, 0)
  // Driving + on duty, as a decimal ("10.5"): the recap figure that gets circled
  const onDutyDecimal = fmtHours((minutes.driving + minutes.on_duty) / 60)

  // ---- graph line -----------------------------------------------------------
  const segs = [...log.segments].sort((a, b) => a.start - b.start)
  const path: string[] = []
  segs.forEach((s, i) => {
    const y = rowCenter(rowIndex(s.status))
    if (i === 0) path.push(`M ${x(s.start)} ${y}`)
    else path.push(`L ${x(s.start)} ${y}`)
    path.push(`L ${x(s.end)} ${y}`)
  })

  const hourLabels = Array.from({ length: 25 }, (_, h) => {
    if (h === 0 || h === 24) return null
    if (h === 12) return 'Noon'
    return String(h % 12)
  })

  const downloadPng = () => {
    const svg = svgRef.current
    if (!svg) return
    // The live sheet is sized with width="100%". Firefox and Safari cannot work
    // out an intrinsic size from that, so rasterise a clone with real pixels.
    const clone = svg.cloneNode(true) as SVGSVGElement
    clone.setAttribute('width', String(W))
    clone.setAttribute('height', String(H))
    const xml = new XMLSerializer().serializeToString(clone)
    const url = URL.createObjectURL(new Blob([xml], { type: 'image/svg+xml' }))
    const img = new Image()
    img.onload = () => {
      const scale = 2
      const canvas = document.createElement('canvas')
      canvas.width = W * scale
      canvas.height = H * scale
      const ctx = canvas.getContext('2d')!
      ctx.fillStyle = '#fff'
      ctx.fillRect(0, 0, canvas.width, canvas.height)
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
      URL.revokeObjectURL(url)
      canvas.toBlob((blob) => {
        if (!blob) return
        const a = document.createElement('a')
        a.href = URL.createObjectURL(blob)
        a.download = `daily-log-${log.date}.png`
        a.click()
        URL.revokeObjectURL(a.href)
      })
    }
    img.src = url
  }

  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-3 print:hidden">
        <p className="text-sm text-slate-500">
          Day {log.day} · {log.from} → {log.to}
        </p>
        <button
          type="button"
          onClick={downloadPng}
          className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 shadow-sm transition hover:bg-slate-50"
        >
          Download PNG
        </button>
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <svg
          ref={svgRef}
          xmlns="http://www.w3.org/2000/svg"
          viewBox={`0 0 ${W} ${H}`}
          width="100%"
          style={{ minWidth: 720, display: 'block' }}
          role="img"
          aria-label={`Driver's daily log for ${log.date}`}
        >
          <rect width={W} height={H} fill="#fff" />

          {/* ---------------- header ---------------- */}
          <T x={30} y={44} size={28} weight={700}>
            Drivers Daily Log
          </T>
          <T x={30} y={60} size={11}>
            (24 hours)
          </T>

          <Field x={290} y={44} width={70} value={month} caption="(month)" align="middle" />
          <T x={366} y={44} size={16}>/</T>
          <Field x={376} y={44} width={70} value={day} caption="(day)" align="middle" />
          <T x={452} y={44} size={16}>/</T>
          <Field x={462} y={44} width={80} value={year} caption="(year)" align="middle" />

          <T x={600} y={30} size={10}>Original - File at home terminal.</T>
          <T x={600} y={44} size={10}>Duplicate - Driver retains in his/her</T>
          <T x={600} y={57} size={10}>possession for 8 days.</T>

          <T x={30} y={104} size={14} weight={700}>From:</T>
          <Field x={75} y={104} width={290} value={log.from} />
          <T x={390} y={104} size={14} weight={700}>To:</T>
          <Field x={420} y={104} width={290} value={log.to} />

          {/* mileage boxes */}
          {[
            { bx: 30, caption: 'Total Miles Driving Today' },
            { bx: 160, caption: 'Total Mileage Today' },
          ].map(({ bx, caption }) => (
            <g key={bx}>
              <rect x={bx} y={126} width={120} height={44} fill="none" stroke={INK} strokeWidth={1.2} />
              <T x={bx + 60} y={155} size={20} weight={700} anchor="middle" fill="#1e3a8a">
                {Math.round(log.miles).toLocaleString('en-US')}
              </T>
              <T x={bx + 60} y={184} size={9} anchor="middle">{caption}</T>
            </g>
          ))}

          <Field x={30} y={222} width={250} value={clip(log.truck, 34)} />
          <T x={155} y={236} size={9} anchor="middle">Truck/Tractor and Trailer Numbers or</T>
          <T x={155} y={247} size={9} anchor="middle">License Plate(s)/State (show each unit)</T>

          <Field x={340} y={146} width={530} value={clip(log.carrier, 60)} caption="Name of Carrier or Carriers" align="middle" />
          <Field x={340} y={190} width={530} value={clip(log.office, 60)} caption="Main Office Address" align="middle" />
          <Field x={340} y={234} width={530} value={clip(log.home_terminal, 60)} caption="Home Terminal Address" align="middle" />

          {/* ---------------- graph grid ---------------- */}
          {/* hour labels */}
          {hourLabels.map((label, h) =>
            label ? (
              <T key={h} x={x(h)} y={GRID_Y - 7} size={h === 12 ? 10 : 11} weight={600} anchor="middle">
                {label}
              </T>
            ) : (
              <g key={h}>
                <T x={x(h)} y={GRID_Y - 19} size={9} anchor="middle">Mid-</T>
                <T x={x(h)} y={GRID_Y - 8} size={9} anchor="middle">night</T>
              </g>
            ),
          )}
          <T x={GRID_X + GRID_W + 38} y={GRID_Y - 19} size={9} anchor="middle">Total</T>
          <T x={GRID_X + GRID_W + 38} y={GRID_Y - 8} size={9} anchor="middle">Hours</T>

          {/* row backgrounds + labels */}
          {ROWS.map((row, i) => (
            <g key={row.status}>
              <rect
                x={GRID_X}
                y={GRID_Y + i * ROW_H}
                width={GRID_W}
                height={ROW_H}
                fill={i % 2 === 0 ? '#f8fafc' : '#fff'}
                stroke={INK}
                strokeWidth={1.2}
              />
              {row.label.map((line, li) => (
                <T
                  key={line}
                  x={30}
                  y={rowCenter(i) + 4 + (li - (row.label.length - 1) / 2) * 12}
                  size={11}
                  weight={600}
                >
                  {line}
                </T>
              ))}
            </g>
          ))}

          {/* vertical hour lines and quarter-hour ticks */}
          {Array.from({ length: 25 }, (_, h) => (
            <line key={`h${h}`} x1={x(h)} x2={x(h)} y1={GRID_Y} y2={gridBottom} stroke="#64748b" strokeWidth={h % 12 === 0 ? 1.2 : 0.6} />
          ))}
          {ROWS.flatMap((_, i) =>
            Array.from({ length: 96 }, (_, q) => {
              if (q % 4 === 0) return null
              const len = q % 2 === 0 ? 11 : 6
              const top = GRID_Y + (i + 1) * ROW_H
              return (
                <line key={`t${i}-${q}`} x1={x(q / 4)} x2={x(q / 4)} y1={top - len} y2={top} stroke="#475569" strokeWidth={0.7} />
              )
            }),
          )}

          {/* the duty-status line */}
          <path d={path.join(' ')} fill="none" stroke={LINE} strokeWidth={3} strokeLinejoin="miter" strokeLinecap="butt" />

          {/* Brackets: on-duty time spent standing still (loading, fueling...) is
              marked with a "cup" under the line - the truck did not move. */}
          {segs
            .filter((sg) => sg.status === 'on_duty')
            .map((sg, i) => {
              const yc = rowCenter(rowIndex('on_duty'))
              return (
                <path
                  key={`br-${i}`}
                  d={`M ${x(sg.start)} ${yc + 4} V ${yc + 11} H ${x(sg.end)} V ${yc + 4}`}
                  fill="none"
                  stroke={LINE}
                  strokeWidth={1.8}
                />
              )
            })}

          {/* totals */}
          {ROWS.map((row, i) => (
            <g key={`tot-${row.status}`}>
              <line x1={GRID_X + GRID_W + 10} x2={GRID_X + GRID_W + 68} y1={rowCenter(i) + 8} y2={rowCenter(i) + 8} stroke={INK} strokeWidth={0.8} />
              <T x={GRID_X + GRID_W + 39} y={rowCenter(i) + 5} size={12} weight={700} anchor="middle" fill="#1e3a8a">
                {fmtHM(minutes[row.status])}
              </T>
            </g>
          ))}
          <T x={GRID_X + GRID_W + 8} y={gridBottom + 22} size={13} weight={700}>=</T>
          <T x={GRID_X + GRID_W + 39} y={gridBottom + 22} size={13} weight={700} anchor="middle" fill="#1e3a8a">
            {fmtHM(totalMinutes)}
          </T>

          {/* ---------------- remarks ---------------- */}
          <T x={30} y={remarksTop - 6} size={14} weight={700}>Remarks</T>
          <rect x={30} y={remarksTop} width={W - 60} height={remarksH} fill="none" stroke={INK} strokeWidth={1.2} />
          {/* A 45-degree flag at every duty-status change: city, state and what
              the driver was doing (pre-trip, loading, fueling...). */}
          {log.remarks.map((r, i) => {
            const rx = x(r.hour)
            const activity = FLAG_ACTIVITY[r.kind] ?? r.text
            return (
              <g key={i}>
                <line x1={rx} x2={rx} y1={gridBottom} y2={remarksTop + 12} stroke="#475569" strokeWidth={0.8} strokeDasharray="2 2" />
                <T
                  x={rx + 2}
                  y={remarksTop + 20}
                  size={9}
                  weight={600}
                  fill="#1e3a8a"
                  transform={`rotate(45 ${rx + 2} ${remarksTop + 20})`}
                >
                  {clip(`${r.location} - ${activity}`, 40)}
                </T>
              </g>
            )
          })}

          {/* ---------------- shipping documents ---------------- */}
          <T x={30} y={shippingY} size={12} weight={700}>Shipping Documents:</T>
          <Field x={170} y={shippingY} width={330} value={clip(log.shipping, 46)} caption="DVL or Manifest No. or Shipper & Commodity" align="middle" />
          <T x={520} y={shippingY} size={10}>
            Enter name of place you reported and where released from work
          </T>
          <T x={520} y={shippingY + 13} size={10}>
            and when and where each change of duty status occurred.
          </T>
          <T x={520} y={shippingY + 26} size={10} weight={700}>
            Use time standard of home terminal.
          </T>

          {/* ---------------- signature and co-driver ---------------- */}
          <T x={30} y={signatureY - 6} size={12} weight={700}>Driver&rsquo;s signature:</T>
          <line x1={165} x2={470} y1={signatureY} y2={signatureY} stroke={INK} strokeWidth={0.9} />
          {log.driver && (
            <text
              x={175}
              y={signatureY - 5}
              fontSize={20}
              fill="#1e3a8a"
              fontStyle="italic"
              fontFamily="'Snell Roundhand', 'Brush Script MT', 'Segoe Script', cursive"
            >
              {clip(log.driver, 30)}
            </text>
          )}
          <T x={317} y={signatureY + 12} size={9} anchor="middle">
            I certify that these entries are true and correct
          </T>
          <T x={500} y={signatureY - 6} size={12} weight={700}>Co-driver:</T>
          <Field x={575} y={signatureY} width={295} value={clip(log.co_driver, 36)} caption="(Name of co-driver)" align="middle" />

          {/* ---------------- duty status changes ---------------- */}
          <T x={30} y={tableTop} size={11} weight={700}>Duty status changes</T>
          <line x1={30} x2={W - 30} y1={tableTop + 5} y2={tableTop + 5} stroke="#cbd5e1" />
          {log.remarks.map((r, i) => (
            <g key={`row-${i}`}>
              <T x={30} y={tableTop + 20 + i * rowGap} size={10} weight={600}>{fmtHour(r.hour)}</T>
              <T x={110} y={tableTop + 20 + i * rowGap} size={10}>{clip(r.location, 34)}</T>
              <T x={330} y={tableTop + 20 + i * rowGap} size={10} fill="#334155">{r.text}</T>
            </g>
          ))}

          {/* ---------------- recap ---------------- */}
          <g transform={`translate(0 ${recapTop})`}>
            <rect x={30} y={0} width={W - 60} height={128} fill="#f8fafc" stroke={INK} strokeWidth={1.2} />
            <T x={42} y={20} size={12} weight={700}>Recap: Complete at end of day</T>
            <T x={42} y={36} size={9.5}>70 Hour / 8 Day Drivers</T>

            <g>
              <T x={42} y={60} size={10} weight={600}>On duty hours today,</T>
              <T x={42} y={72} size={10} weight={600}>Total lines 3 &amp; 4</T>
              {/* driving + on duty written as a decimal and circled */}
              <ellipse cx={150} cy={97} rx={36} ry={19} fill="none" stroke="#1e3a8a" strokeWidth={2} />
              <T x={150} y={104} size={24} weight={700} anchor="middle" fill="#1e3a8a">
                {onDutyDecimal}
              </T>
            </g>
            {[
              { cx: 280, key: 'A', text: ['A. Total hours on duty last', '7 days including today.'], value: log.recap.a },
              { cx: 500, key: 'B', text: ['B. Total hours available', 'tomorrow, 70 hr. minus A*'], value: log.recap.b },
              { cx: 720, key: 'C', text: ['C. Total hours on duty last', '8 days including today.'], value: log.recap.c },
            ].map(({ cx, key, text, value }) => (
              <g key={key}>
                <T x={cx - 70} y={60} size={10} weight={600}>{text[0]}</T>
                <T x={cx - 70} y={72} size={10} weight={600}>{text[1]}</T>
                <T x={cx} y={104} size={24} weight={700} anchor="middle" fill="#1e3a8a">
                  {fmtHours(value)}
                </T>
              </g>
            ))}
            <T x={W - 42} y={120} size={9} anchor="end">
              *If you took 34 consecutive hours off duty you have 70 hours available.
            </T>
          </g>
        </svg>
      </div>
    </div>
  )
}
