// A little CSS-only desk creature for each agent (no images).
import type { AgentName } from '../api'
import { AGENTS } from '../agents'

export type Mood = 'idle' | 'working' | 'done' | 'blocked'

export function Avatar({ agent, mood, size = 64 }: { agent: AgentName; mood: Mood; size?: number }) {
  const meta = AGENTS[agent]
  return (
    <div
      className={`critter critter--${agent.toLowerCase()} is-${mood}`}
      style={{ ['--hue' as string]: meta.hue, ['--s' as string]: `${size}px` }}
      aria-hidden
    >
      <div className="critter__gear" />
      <div className="critter__body">
        <span className="critter__ear critter__ear--l" />
        <span className="critter__ear critter__ear--r" />
        <span className="critter__eye critter__eye--l" />
        <span className="critter__eye critter__eye--r" />
        <span className="critter__blush critter__blush--l" />
        <span className="critter__blush critter__blush--r" />
        <span className="critter__mouth" />
      </div>
      <div className="critter__shadow" />
    </div>
  )
}
