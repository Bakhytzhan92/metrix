'use client'

import Link from 'next/link'
import type { CSSProperties, MouseEvent } from 'react'

const baseLinkStyle: CSSProperties = {
  color: '#111',
  textDecoration: 'none',
  padding: '6px 12px',
  borderRadius: 6,
  transition: 'background-color 0.15s ease',
}

const hoverBackground = '#e5e5e5'

function NavLink({
  href,
  children,
}: {
  href: string
  children: React.ReactNode
}) {
  const handleEnter = (event: MouseEvent<HTMLAnchorElement>) => {
    event.currentTarget.style.backgroundColor = hoverBackground
  }

  const handleLeave = (event: MouseEvent<HTMLAnchorElement>) => {
    event.currentTarget.style.backgroundColor = 'transparent'
  }

  return (
    <Link
      href={href}
      style={baseLinkStyle}
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
    >
      {children}
    </Link>
  )
}

export default function Navbar() {
  return (
    <nav
      style={{
        padding: 12,
        background: '#f6f6f6',
        borderBottom: '1px solid #e5e5e5',
        fontFamily: 'sans-serif',
      }}
    >
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <NavLink href="/">Проекты</NavLink>
        <NavLink href="/users">Пользователи</NavLink>
        <NavLink href="/tasks">Задачи</NavLink>
      </div>
    </nav>
  )
}
