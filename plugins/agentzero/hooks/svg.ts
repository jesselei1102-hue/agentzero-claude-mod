import type { BandModel, PillTone } from './band'
import type { Card } from './cards'
import { KIND_LABEL, type PaneRow } from './pane'

export const PALETTE: Record<PillTone, { fg: string; bg: string }> = {
  ink: { fg: '#FFFFFF', bg: '#1F2937' },
  green: { fg: '#2E7D32', bg: '#E8F5E9' },
  amber: { fg: '#B26A00', bg: '#FFF4E0' },
  grey: { fg: '#6B7280', bg: '#F3F4F6' },
  blue: { fg: '#1565C0', bg: '#E8F0FE' },
  red: { fg: '#C62828', bg: '#FDECEA' },
}
export const INK = '#1F2937'
export const MUTED = '#6B7280'
export const FONT = '-apple-system,BlinkMacSystemFont,"PingFang SC",system-ui,sans-serif'
const TRACK = '#E5E7EB'

export function escapeXml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&apos;')
}

export function textWidth(s: string, size: number): number {
  let w = 0
  for (const ch of Array.from(s)) w += (ch.codePointAt(0) ?? 0) >= 0x2e80 ? size : size * 0.6
  return Math.ceil(w)
}

function cut(s: string, n: number): string {
  const a = Array.from(s)
  return a.length > n ? a.slice(0, n - 1).join('') + '…' : s
}

const BREAK_AFTER = new Set(['，', '。', '、', '；', '：', ',', '.', ';', ':', '）', ')', ' '])

export function wrap(s: string, perLine: number, maxLines: number): string[] {
  let rest = Array.from(s.trim())
  const lines: string[] = []
  while (rest.length > 0 && lines.length < maxLines) {
    if (rest.length <= perLine) {
      lines.push(rest.join(''))
      break
    }
    if (lines.length === maxLines - 1) {
      lines.push(rest.slice(0, perLine - 1).join('') + '…')
      break
    }
    let at = perLine
    for (let i = perLine - 1; i >= perLine - 6 && i >= 0; i--) {
      if (BREAK_AFTER.has(rest[i])) {
        at = i + 1
        break
      }
    }
    lines.push(rest.slice(0, at).join('').trimEnd())
    rest = Array.from(rest.slice(at).join('').trimStart())
  }
  return lines
}

function svg(width: number, height: number, body: string): string {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" font-family='${FONT}'>${body}</svg>`
}

function text(x: number, y: number, s: string, size: number, fill: string, extra = ''): string {
  return `<text x="${x}" y="${y}" font-size="${size}" fill="${fill}"${extra}>${escapeXml(s)}</text>`
}

// A rounded chip with centred text; returns its width so callers can lay out the next one.
function chip(x: number, y: number, label: string, fg: string, bg: string, size = 12): { w: number; svg: string } {
  const w = textWidth(label, size) + 20
  return {
    w,
    svg: `<rect x="${x}" y="${y}" rx="11" width="${w}" height="22" fill="${bg}"/>` +
      text(x + w / 2, y + 15.5, label, size, fg, ' text-anchor="middle" font-weight="600"'),
  }
}

export function bandSvg(m: BandModel): string {
  let x = 0
  let body = ''
  for (const p of m.pills) {
    const c = chip(x, 3, p.tone === 'ink' ? `● ${p.text}` : p.text, PALETTE[p.tone].fg, PALETTE[p.tone].bg)
    body += c.svg
    x += c.w + 8
  }
  if (m.ring !== null) {
    const r = 9
    const cx = x + r + 2
    const len = 2 * Math.PI * r
    const arc = m.ring.tone === 'amber' ? PALETTE.amber.fg : PALETTE.blue.fg
    body += `<circle cx="${cx}" cy="14" r="${r}" fill="none" stroke="${TRACK}" stroke-width="4"/>`
    body += `<circle cx="${cx}" cy="14" r="${r}" fill="none" stroke="${arc}" stroke-width="4" stroke-linecap="round" stroke-dasharray="${((len * m.ring.percent) / 100).toFixed(1)} ${len.toFixed(1)}" transform="rotate(-90 ${cx} 14)"/>`
    const label = `上下文 ${m.ring.percent}%`
    body += text(cx + 16, 18, label, 12, MUTED)
    x = cx + 16 + textWidth(label, 12)
    if (m.ring.note !== null) {
      const note = ` · ${m.ring.note}`
      body += text(x, 18, note, 12, PALETTE.amber.fg)
      x += textWidth(note, 12)
    }
  }
  return svg(x + 8, 28, body)
}

export function paneHeaderSvg(open: number, done: number): string {
  const a = chip(0, 30, `${open} 条待确认`, open > 0 ? PALETTE.amber.fg : PALETTE.grey.fg, open > 0 ? PALETTE.amber.bg : PALETTE.grey.bg)
  const b = chip(a.w + 8, 30, `${done} 条已处理`, PALETTE.grey.fg, PALETTE.grey.bg)
  return svg(
    360,
    58,
    text(0, 18, '待你确认', 17, INK, ' font-weight="700"') + text(86, 18, '助手推断的内容，等你点头才算数', 12, MUTED) + a.svg + b.svg,
  )
}

const ITEM_STYLE: Record<PaneRow['state'], { fg: string; fill: string }> = {
  open: { fg: PALETTE.amber.fg, fill: '#FFFBF3' },
  kept: { fg: PALETTE.green.fg, fill: PALETTE.green.bg },
  rejected: { fg: PALETTE.grey.fg, fill: '#F7F7F8' },
  failed: { fg: PALETTE.red.fg, fill: PALETTE.red.bg },
}

export function pendingItemSvg(row: PaneRow): string {
  const { fg, fill } = ITEM_STYLE[row.state]
  const lines = wrap(row.item.sentence, 18, 2)
  const h = 74 + 20 * (lines.length - 1)
  const k = chip(14, 14, KIND_LABEL[row.item.kind] ?? row.item.kind, fg, '#FFFFFF')
  let body = `<rect x="0.5" y="0.5" width="359" height="${h + 21}" rx="14" fill="${fill}" stroke="${fg}" stroke-opacity="0.22"/>` + k.svg
  if (row.item.createdAt !== null) body += text(14 + k.w + 10, 29.5, row.item.createdAt.slice(5, 16).replace('T', ' '), 11.5, MUTED)
  if (row.state === 'kept' || row.state === 'rejected') {
    body += text(346, 29.5, row.state === 'kept' ? '✓ 已保留' : '✗ 已拒绝', 12, fg, ' text-anchor="end" font-weight="700"')
  }
  const strike = row.state === 'rejected' ? ' text-decoration="line-through"' : ''
  lines.forEach((line, i) => {
    body += text(14, 58 + 20 * i, line, 14.5, row.state === 'open' ? INK : MUTED, ` font-weight="700"${strike}`)
  })
  body += row.state === 'failed' && row.message !== null
    ? text(14, h + 8, cut(row.message, 44), 12, PALETTE.red.fg)
    : text(14, h + 8, cut(row.item.provenance, 44), 12, MUTED)
  return svg(360, h + 22, body)
}

export function cardSvg(card: Card): string {
  const tone = PALETTE[card.tone]
  const stroke = card.outline
    ? `stroke="${MUTED}" stroke-opacity="0.6" stroke-dasharray="4 3"`
    : `stroke="${tone.fg}" stroke-opacity="0.18"`
  const label = chip(60, 12, card.label, tone.fg, '#FFFFFF')
  let body = `<rect x="0.5" y="0.5" width="639" height="67" rx="14" fill="${tone.bg}" ${stroke}/>`
  body += `<circle cx="32" cy="34" r="18" fill="#FFFFFF"/>` + text(32, 40, card.icon, 17, INK, ' text-anchor="middle"')
  body += label.svg + text(60 + label.w + 10, 28, cut(card.title, 30), 15, INK, ' font-weight="700"')
  if (card.detail !== null) body += text(60, 54, cut(card.detail, 44), 12.5, MUTED)
  return svg(640, 68, body)
}
