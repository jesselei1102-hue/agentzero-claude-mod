import type { Register } from 'claude-code'
import { registerHotSet } from './feature-hotset'

export const register: Register = on => {
  registerHotSet(on)
}
