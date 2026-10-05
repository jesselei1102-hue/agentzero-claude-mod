import type { Register } from 'claude-code'
import { registerCommand } from './command'
import { registerHotSet } from './feature-hotset'
import { registerHud } from './feature-hud'
import { registerSaidCheck } from './feature-said'

export const register: Register = on => {
  registerHotSet(on)
  registerSaidCheck(on)
  registerCommand(on)
  registerHud(on)
}
