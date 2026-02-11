"use client"

import type { ReactNode } from "react"

type ListKind = "ul" | "ol"

function renderInline(text: string): ReactNode[] {
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*|\*[^*\n]+\*)/g)
  return parts.filter(Boolean).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={index}>{part.slice(2, -2)}</strong>
    }
    if (part.startsWith("*") && part.endsWith("*")) {
      return <em key={index}>{part.slice(1, -1)}</em>
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return (
        <code key={index} className="rounded bg-muted/60 px-1 py-0.5 text-[0.9em]">
          {part.slice(1, -1)}
        </code>
      )
    }
    return part
  })
}

export function ChatMarkdown({ content }: { content: string }) {
  const lines = content.replace(/\r\n/g, "\n").split("\n")
  const blocks: ReactNode[] = []
  let listItems: string[] = []
  let listKind: ListKind | null = null

  const flushList = () => {
    if (!listItems.length || !listKind) return

    if (listKind === "ul") {
      blocks.push(
        <ul key={`ul-${blocks.length}`} className="list-disc pl-5 space-y-1">
          {listItems.map((item, index) => (
            <li key={index}>{renderInline(item)}</li>
          ))}
        </ul>
      )
    } else {
      blocks.push(
        <ol key={`ol-${blocks.length}`} className="list-decimal pl-5 space-y-1">
          {listItems.map((item, index) => (
            <li key={index}>{renderInline(item)}</li>
          ))}
        </ol>
      )
    }

    listItems = []
    listKind = null
  }

  lines.forEach((rawLine, index) => {
    const line = rawLine.trimEnd()
    const trimmed = line.trim()

    if (!trimmed) {
      flushList()
      return
    }

    const headingMatch = trimmed.match(/^(#{1,3})\s+(.+)$/)
    if (headingMatch) {
      flushList()
      const level = headingMatch[1].length
      const text = headingMatch[2]
      if (level === 1) {
        blocks.push(
          <h1 key={`h1-${index}`} className="text-lg font-semibold">
            {renderInline(text)}
          </h1>
        )
      } else if (level === 2) {
        blocks.push(
          <h2 key={`h2-${index}`} className="text-base font-semibold">
            {renderInline(text)}
          </h2>
        )
      } else {
        blocks.push(
          <h3 key={`h3-${index}`} className="text-sm font-semibold">
            {renderInline(text)}
          </h3>
        )
      }
      return
    }

    if (/^-{3,}$/.test(trimmed)) {
      flushList()
      blocks.push(<hr key={`hr-${index}`} className="border-border/50" />)
      return
    }

    const ulMatch = trimmed.match(/^[-*]\s+(.+)$/)
    if (ulMatch) {
      if (listKind && listKind !== "ul") flushList()
      listKind = "ul"
      listItems.push(ulMatch[1])
      return
    }

    const olMatch = trimmed.match(/^\d+\.\s+(.+)$/)
    if (olMatch) {
      if (listKind && listKind !== "ol") flushList()
      listKind = "ol"
      listItems.push(olMatch[1])
      return
    }

    flushList()
    blocks.push(
      <p key={`p-${index}`} className="whitespace-pre-wrap">
        {renderInline(line)}
      </p>
    )
  })

  flushList()

  return <div className="space-y-2">{blocks}</div>
}
