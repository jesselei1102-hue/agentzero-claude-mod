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
// Width of a card's detail line, in px at 12.5 px: the card is 640 wide, the line starts at 60.
export const CARD_DETAIL_PX = 564

export function escapeXml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&apos;')
}

export function textWidth(s: string, size: number): number {
  let w = 0
  for (const ch of Array.from(s)) w += (ch.codePointAt(0) ?? 0) >= 0x2e80 ? size : size * 0.6
  return Math.ceil(w)
}

export function cutToWidth(s: string, maxPx: number, size: number): string {
  if (textWidth(s, size) <= maxPx) return s
  const a = Array.from(s)
  let n = a.length
  while (n > 0 && textWidth(a.slice(0, n).join('') + '…', size) > maxPx) n--
  return a.slice(0, n).join('') + '…'
}

const BREAK_AFTER = new Set(['，', '。', '、', '；', '：', ',', '.', ';', ':', '）', ')', ' '])
const BREAK_WINDOW = 8

// Lines of at most maxPx at this font size: a break after punctuation or a space near the
// end of a line when there is one; the last allowed line is cut with "…".
export function wrap(s: string, maxPx: number, size: number, maxLines: number): string[] {
  let rest = Array.from(s.trim())
  const lines: string[] = []
  while (rest.length > 0 && lines.length < maxLines) {
    const text = rest.join('')
    if (textWidth(text, size) <= maxPx) {
      lines.push(text)
      break
    }
    if (lines.length === maxLines - 1) {
      lines.push(cutToWidth(text, maxPx, size))
      break
    }
    let fit = 0
    while (fit < rest.length && textWidth(rest.slice(0, fit + 1).join(''), size) <= maxPx) fit++
    let at = Math.max(fit, 1)
    for (let i = fit - 1; i >= fit - BREAK_WINDOW && i >= 0; i--) {
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
    const label = `context ${m.ring.percent}%`
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
  const a = chip(0, 48, `${open} waiting`, open > 0 ? PALETTE.amber.fg : PALETTE.grey.fg, open > 0 ? PALETTE.amber.bg : PALETTE.grey.bg)
  const b = chip(a.w + 8, 48, `${done} done`, PALETTE.grey.fg, PALETTE.grey.bg)
  return svg(
    360,
    76,
    text(0, 18, 'Waiting for you', 17, INK, ' font-weight="700"') +
      text(0, 38, 'The assistant inferred these. Keep or reject each one.', 12, MUTED) +
      a.svg +
      b.svg,
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
  const lines = wrap(row.item.sentence, 332, 14.5, 2)
  const h = 74 + 20 * (lines.length - 1)
  const k = chip(14, 14, KIND_LABEL[row.item.kind] ?? row.item.kind, fg, '#FFFFFF')
  let body = `<rect x="0.5" y="0.5" width="359" height="${h + 21}" rx="14" fill="${fill}" stroke="${fg}" stroke-opacity="0.22"/>` + k.svg
  if (row.item.createdAt !== null) body += text(14 + k.w + 10, 29.5, row.item.createdAt.slice(5, 16).replace('T', ' '), 11.5, MUTED)
  if (row.state === 'kept' || row.state === 'rejected') {
    body += text(346, 29.5, row.state === 'kept' ? '✓ Kept' : '✗ Rejected', 12, fg, ' text-anchor="end" font-weight="700"')
  }
  const strike = row.state === 'rejected' ? ' text-decoration="line-through"' : ''
  lines.forEach((line, i) => {
    body += text(14, 58 + 20 * i, line, 14.5, row.state === 'open' ? INK : MUTED, ` font-weight="700"${strike}`)
  })
  body += row.state === 'failed' && row.message !== null
    ? text(14, h + 8, cutToWidth(row.message, 332, 12), 12, PALETTE.red.fg)
    : text(14, h + 8, cutToWidth(row.item.provenance, 332, 12), 12, MUTED)
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
  const titleX = 60 + label.w + 10
  body += label.svg + text(titleX, 28, cutToWidth(card.title, 640 - titleX - 16, 15), 15, INK, ' font-weight="700"')
  if (card.detail !== null) body += text(60, 54, cutToWidth(card.detail, CARD_DETAIL_PX, 12.5), 12.5, MUTED)
  return svg(640, 68, body)
}
