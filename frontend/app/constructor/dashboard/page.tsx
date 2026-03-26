"use client"

import { useState, useEffect, useRef } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import { Progress } from "@/components/ui/progress"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import {
  Zap,
  Upload,
  ArrowUp,
  Loader2,
  FileText,
  Video,
  File,
  CheckCircle2,
  LogOut,
  Bot,
  ChevronRight,
  ChevronDown,
  Activity,
  Circle,
  AlertCircle,
} from "lucide-react"
import { useAuthStore } from "@/lib/store"
import { constructorApi } from "@/lib/api"
import { cn } from "@/lib/utils"
import { ChatMarkdown } from "@/components/chat-markdown"

// ─── Types ────────────────────────────────────────────────────────────────────

interface ChatMessage {
  kind: "message"
  id: string
  role: "user" | "assistant"
  content: string
  timestamp: Date
  isStreaming?: boolean
  streamId?: string
}

interface ActivityToolCall {
  id: string
  tool: string
  args: Record<string, any>
  status: "running" | "complete"
  result: string | null
}

interface ChatSubagentActivity {
  kind: "subagent_activity"
  id: string
  subagent_type: string
  status: "running" | "complete" | "error"
  startedAt: Date
  toolCalls: ActivityToolCall[]
  result: string | null
  error: string | null
  isExpanded: boolean
}

interface ChatTodoComplete {
  kind: "todo_complete"
  id: string
  task: string
  timestamp: Date
}

type ChatItem = ChatMessage | ChatSubagentActivity | ChatTodoComplete

interface UploadedFile {
  id: string
  name: string
  size: number
  type: string
  status: "uploading" | "processing" | "completed" | "error"
}

interface GraphSubagent {
  subagent_type: string
  status: "running" | "complete" | "error"
}

interface Todo {
  id: string
  task: string
  status: "pending" | "in_progress" | "completed"
}

// ─── Constants ────────────────────────────────────────────────────────────────

const KNOWN_SUBAGENTS = [
  { type: "Ingestion Sub-Agent", short: "Ingest" },
  { type: "Structure Sub-Agent", short: "Structure" },
  { type: "Quiz Generation Sub-Agent", short: "Quiz Gen" },
  { type: "Validation Sub-Agent", short: "Validate" },
] as const

// ─── Agent Hierarchy Graph ────────────────────────────────────────────────────

function AgentHierarchyGraph({
  subagents,
  isMainActive,
}: {
  subagents: Map<string, GraphSubagent>
  isMainActive: boolean
}) {
  const getStatus = (type: string) => subagents.get(type)?.status ?? "idle"

  const nodeColors = (status: string) =>
    cn(
      "flex flex-col items-center gap-1 py-2 px-1 rounded-lg border text-center transition-all",
      status === "running" && "border-blue-500/40 bg-blue-500/10",
      status === "complete" && "border-green-500/30 bg-green-500/10",
      status === "error" && "border-red-500/30 bg-red-500/10",
      !["running", "complete", "error"].includes(status) && "border-border/40 bg-muted/20",
    )

  const dotColor = (status: string) =>
    cn(
      "w-1.5 h-1.5 rounded-full shrink-0",
      status === "running" && "bg-blue-400 animate-pulse",
      status === "complete" && "bg-green-400",
      status === "error" && "bg-red-400",
      !["running", "complete", "error"].includes(status) && "bg-muted-foreground/30",
    )

  const labelColor = (status: string) =>
    cn(
      "text-[10px] font-medium leading-tight",
      status === "running" && "text-blue-300",
      status === "complete" && "text-green-300",
      status === "error" && "text-red-300",
      !["running", "complete", "error"].includes(status) && "text-muted-foreground",
    )

  // Sub-agent center x positions as percentages of the row width (4 equal cols)
  const subagentXs = [12.5, 37.5, 62.5, 87.5]

  return (
    <div className="flex flex-col items-center text-xs">
      {/* Main Coordinator node */}
      <div
        className={cn(
          "flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border font-medium transition-all",
          isMainActive
            ? "border-primary/40 bg-primary/10 text-primary"
            : "border-border/40 bg-muted/20 text-muted-foreground",
        )}
      >
        <Bot className="w-3.5 h-3.5 shrink-0" />
        <span>Main Coordinator</span>
        {isMainActive && (
          <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse shrink-0" />
        )}
      </div>

      {/* Connecting lines via SVG */}
      <div className="relative w-full" style={{ height: 36 }}>
        <svg
          className="absolute inset-0 w-full h-full overflow-visible"
          preserveAspectRatio="none"
        >
          {/* Vertical drop from main agent */}
          <line x1="50%" y1="0" x2="50%" y2="50%" stroke="currentColor" strokeOpacity="0.25" strokeWidth="1" />
          {/* Horizontal bar connecting all sub-agents */}
          <line
            x1={`${subagentXs[0]}%`} y1="50%"
            x2={`${subagentXs[subagentXs.length - 1]}%`} y2="50%"
            stroke="currentColor" strokeOpacity="0.25" strokeWidth="1"
          />
          {/* Vertical drops to each sub-agent */}
          {subagentXs.map((x, i) => (
            <line
              key={i}
              x1={`${x}%`} y1="50%"
              x2={`${x}%`} y2="100%"
              stroke="currentColor" strokeOpacity="0.25" strokeWidth="1"
            />
          ))}
        </svg>
      </div>

      {/* Sub-agent nodes in a horizontal row */}
      <div className="w-full grid grid-cols-4 gap-1">
        {KNOWN_SUBAGENTS.map(({ type, short }) => {
          const status = getStatus(type)
          return (
            <div key={type} className={nodeColors(status)}>
              <span className={dotColor(status)} />
              <span className={labelColor(status)}>{short}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ─── Subagent Activity Entry ──────────────────────────────────────────────────

function SubagentActivityEntry({
  activity,
  onToggle,
}: {
  activity: ChatSubagentActivity
  onToggle: (id: string) => void
}) {
  const formatValue = (v: any, maxLen = 400): string => {
    if (v === null || v === undefined) return ""
    if (typeof v === "string") {
      try {
        const parsed = JSON.parse(v)
        const pretty = JSON.stringify(parsed, null, 2)
        return pretty.length > maxLen ? pretty.slice(0, maxLen) + "\n..." : pretty
      } catch {
        return v.length > maxLen ? v.slice(0, maxLen) + "..." : v
      }
    }
    const str = JSON.stringify(v, null, 2)
    return str.length > maxLen ? str.slice(0, maxLen) + "\n..." : str
  }

  const completedCount = activity.toolCalls.filter((t) => t.status === "complete").length

  return (
    <div
      className={cn(
        "rounded-xl border text-xs overflow-hidden",
        activity.status === "running" && "border-blue-500/30 bg-blue-500/5",
        activity.status === "complete" && "border-green-500/20 bg-green-500/5",
        activity.status === "error" && "border-red-500/20 bg-red-500/5",
      )}
    >
      {/* Collapsible header */}
      <button
        className="w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-white/5 transition-colors"
        onClick={() => onToggle(activity.id)}
      >
        {activity.status === "running" ? (
          <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-400 shrink-0" />
        ) : activity.status === "complete" ? (
          <CheckCircle2 className="w-3.5 h-3.5 text-green-400 shrink-0" />
        ) : (
          <AlertCircle className="w-3.5 h-3.5 text-red-400 shrink-0" />
        )}
        <span className="font-medium flex-1">{activity.subagent_type}</span>
        {activity.toolCalls.length > 0 && (
          <span className="text-muted-foreground text-[10px] mr-1">
            {completedCount}/{activity.toolCalls.length} tools
          </span>
        )}
        {activity.isExpanded ? (
          <ChevronDown className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
        )}
      </button>

      {/* Expanded body */}
      {activity.isExpanded && (
        <div className="border-t border-border/20 px-3 py-2.5 space-y-4">
          {activity.toolCalls.length === 0 ? (
            <p className="text-muted-foreground">Initializing...</p>
          ) : (
            activity.toolCalls.map((call) => (
              <div key={call.id} className="space-y-1.5">
                {/* Name + status */}
                <div className="flex items-center gap-1.5">
                  {call.status === "running" ? (
                    <Loader2 className="w-3 h-3 animate-spin text-yellow-400 shrink-0" />
                  ) : (
                    <CheckCircle2 className="w-3 h-3 text-green-400 shrink-0" />
                  )}
                  <span className="font-mono font-semibold text-foreground/90">{call.tool}</span>
                </div>
                {/* Args */}
                {Object.keys(call.args).length > 0 && (
                  <div className="ml-4 rounded-md bg-muted/40 border border-border/30 p-2 space-y-0.5">
                    <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">
                      Input
                    </p>
                    <pre className="font-mono text-[10px] text-foreground/60 whitespace-pre-wrap break-all leading-relaxed">
                      {formatValue(call.args)}
                    </pre>
                  </div>
                )}
                {/* Result */}
                {call.result && (
                  <div className="ml-4 rounded-md bg-green-950/30 border border-green-500/20 p-2 space-y-0.5">
                    <p className="text-[10px] uppercase tracking-wider text-green-400/70 font-medium">
                      Result
                    </p>
                    <pre className="font-mono text-[10px] text-foreground/60 whitespace-pre-wrap break-all leading-relaxed">
                      {formatValue(call.result)}
                    </pre>
                  </div>
                )}
              </div>
            ))
          )}
          {activity.error && (
            <div className="rounded-md bg-red-950/30 border border-red-500/20 p-2 text-red-300">
              {activity.error}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Main Dashboard ───────────────────────────────────────────────────────────

export default function ConstructorDashboard() {
  const router = useRouter()
  const { creatorId, creatorToken, logout, _hasHydrated } = useAuthStore()

  const [chatItems, setChatItems] = useState<ChatItem[]>([])
  const [inputMessage, setInputMessage] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [isConnected, setIsConnected] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [courseId, setCourseId] = useState<number | null>(null)
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([])
  const [isStoreHydrated, setIsStoreHydrated] = useState(false)
  const [currentAgent, setCurrentAgent] = useState<string>("")
  const [isAgentThinking, setIsAgentThinking] = useState(false)
  const [subagents, setSubagents] = useState<Map<string, GraphSubagent>>(new Map())
  const [todos, setTodos] = useState<Todo[]>([])
  const [questionModal, setQuestionModal] = useState<{
    isOpen: boolean
    questionId: string | null
    question: string
    choices: string[]
    otherValue: string
    threadId: string | null
  }>({
    isOpen: false,
    questionId: null,
    question: "",
    choices: [],
    otherValue: "",
    threadId: null,
  })

  const chatEndRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const initRequestIdRef = useRef(0)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const allowReconnectRef = useRef(true)
  const prevTodosRef = useRef<Todo[]>([])

  // Is the main coordinator the active agent (no subagent running)?
  const isMainActive =
    isConnected &&
    (currentAgent === "Main Coordinator" ||
      (isAgentThinking && !Array.from(subagents.values()).some((s) => s.status === "running")))

  // ── Lifecycle ──────────────────────────────────────────────────────────────

  useEffect(() => {
    if (_hasHydrated && !creatorToken) {
      router.push("/auth/login")
      return
    }
    if (_hasHydrated && creatorToken) initializeSession()
    return () => {
      allowReconnectRef.current = false
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
      initRequestIdRef.current += 1
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [_hasHydrated, creatorToken])

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [chatItems])

  useEffect(() => {
    if (_hasHydrated) setIsStoreHydrated(true)
  }, [_hasHydrated])

  useEffect(() => {
    const textarea = textareaRef.current
    if (!textarea) return
    const resize = () => {
      textarea.style.height = "auto"
      textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`
    }
    resize()
    textarea.addEventListener("input", resize)
    return () => textarea.removeEventListener("input", resize)
  }, [inputMessage])

  // ── Session & WebSocket ────────────────────────────────────────────────────

  const initializeSession = async () => {
    const requestId = ++initRequestIdRef.current
    try {
      const response = await constructorApi.startSession()
      if (requestId !== initRequestIdRef.current) return
      setSessionId(response.session_id)
      setCourseId(response.course_id)
      setChatItems([
        {
          kind: "message",
          id: "welcome",
          role: "assistant",
          content:
            response.message ||
            "Hello! I'm your Course Constructor Assistant. Let's build a course together!",
          timestamp: new Date(),
        },
      ])
      connectWebSocket(response.session_id)
    } catch {
      if (requestId !== initRequestIdRef.current) return
      toast.error("Failed to initialize session")
    }
  }

  const resolveWebSocketBase = () => {
    const wsProtocol = window.location.protocol === "https:" ? "wss" : "ws"
    const configuredBase = process.env.NEXT_PUBLIC_WS_URL || process.env.NEXT_PUBLIC_API_URL
    if (configuredBase) {
      try {
        const url = new URL(configuredBase)
        if (url.port === "3000" && (url.hostname === "localhost" || url.hostname === "127.0.0.1")) {
          return `${wsProtocol}://localhost:8000`
        }
        return `${url.protocol === "https:" ? "wss" : "ws"}://${url.host}`
      } catch {}
    }
    return `${wsProtocol}://${window.location.hostname}:8000`
  }

  const connectWebSocket = (sid: string) => {
    if (
      wsRef.current &&
      (wsRef.current.readyState === WebSocket.OPEN ||
        wsRef.current.readyState === WebSocket.CONNECTING)
    )
      return
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }

    const wsBase = resolveWebSocketBase()
    wsRef.current = new WebSocket(`${wsBase}/api/v1/constructor/session/ws/${sid}`)

    wsRef.current.onopen = () => {
      setIsConnected(true)
      reconnectAttemptsRef.current = 0
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
    }

    wsRef.current.onmessage = (event) => {
      console.log("WS:", event.data)
      const data = JSON.parse(event.data)

      // ── token ──────────────────────────────────────────────────────────────
      if (data.type === "token") {
        setIsLoading(false)
        const isFirst = Boolean(data.metadata?.is_first)
        const isLast = Boolean(data.metadata?.is_last)
        const streamId = String(data.metadata?.stream_id || "")

        setChatItems((prev) => {
          if (isFirst) {
            const last = prev[prev.length - 1]
            if (
              last?.kind === "message" &&
              (last as ChatMessage).role === "assistant" &&
              (last as ChatMessage).isStreaming &&
              (last as ChatMessage).streamId === streamId
            )
              return prev
            return [
              ...prev,
              {
                kind: "message",
                id: Date.now().toString(),
                role: "assistant",
                content: data.content,
                timestamp: new Date(),
                isStreaming: !isLast,
                streamId,
              } as ChatMessage,
            ]
          }
          // Find existing streaming message
          let streamIdx = -1
          for (let i = prev.length - 1; i >= 0; i--) {
            const item = prev[i]
            if (
              item.kind === "message" &&
              (item as ChatMessage).role === "assistant" &&
              (item as ChatMessage).isStreaming &&
              (!streamId || (item as ChatMessage).streamId === streamId)
            ) {
              streamIdx = i
              break
            }
          }
          if (streamIdx !== -1) {
            return prev.map((item, i) =>
              i === streamIdx
                ? ({
                    ...item,
                    content: (item as ChatMessage).content + data.content,
                    isStreaming: !isLast,
                  } as ChatMessage)
                : item,
            )
          }
          return [
            ...prev,
            {
              kind: "message",
              id: Date.now().toString(),
              role: "assistant",
              content: data.content,
              timestamp: new Date(),
              isStreaming: !isLast,
              streamId,
            } as ChatMessage,
          ]
        })

      // ── status ─────────────────────────────────────────────────────────────
      } else if (data.type === "status") {
        // No status display in new UI, but we still handle it

      // ── agent_change ───────────────────────────────────────────────────────
      } else if (data.type === "agent_change") {
        setCurrentAgent(data.agent || "")

      // ── agent_thinking ─────────────────────────────────────────────────────
      } else if (data.type === "agent_thinking") {
        setCurrentAgent(data.agent || "")
        setIsAgentThinking(true)

      } else if (data.type === "agent_done_thinking") {
        setIsAgentThinking(false)

      // ── subagent_start ─────────────────────────────────────────────────────
      } else if (data.type === "subagent_start") {
        const subagentType: string = data.subagent_type || "Unknown"
        console.log(`[subagent_start] subagentType="${subagentType}"`)

        setSubagents((prev) => {
          const existing = prev.get(subagentType)
          if (existing && existing.status === "running") return prev
          return new Map(prev).set(subagentType, {
            subagent_type: subagentType,
            status: "running",
          })
        })

        setChatItems((prev) => {
          // Skip if already a running entry for this type
          const alreadyRunning = prev.some(
            (item) =>
              item.kind === "subagent_activity" &&
              (item as ChatSubagentActivity).subagent_type === subagentType &&
              (item as ChatSubagentActivity).status === "running",
          )
          if (alreadyRunning) {
            console.log(`[subagent_start] Already running, skipping`)
            return prev
          }
          const newActivity: ChatSubagentActivity = {
            kind: "subagent_activity",
            id: `${subagentType}-${Date.now()}`,
            subagent_type: subagentType,
            status: "running",
            startedAt: new Date(),
            toolCalls: [],
            result: null,
            error: null,
            isExpanded: true,
          }
          console.log(`[subagent_start] Created new activity for "${subagentType}"`)
          return [...prev, newActivity]
        })

        setCurrentAgent(subagentType)

      // ── subagent_complete ──────────────────────────────────────────────────
      } else if (data.type === "subagent_complete") {
        const completedType: string = data.subagent_id || ""

        setSubagents((prev) => {
          const updated = new Map(prev)
          const sa = updated.get(completedType)
          if (sa) updated.set(completedType, { ...sa, status: "complete" })
          return updated
        })

        setChatItems((prev) => {
          let lastRunningIdx = -1
          for (let i = 0; i < prev.length; i++) {
            const item = prev[i]
            if (
              item.kind === "subagent_activity" &&
              (item as ChatSubagentActivity).subagent_type === completedType &&
              (item as ChatSubagentActivity).status === "running"
            ) {
              lastRunningIdx = i
            }
          }
          if (lastRunningIdx === -1) return prev
          return prev.map((item, i) =>
            i === lastRunningIdx
              ? ({
                  ...item,
                  status: "complete",
                  result: data.result || null,
                  isExpanded: false,
                } as ChatSubagentActivity)
              : item,
          )
        })

      // ── subagent_error ─────────────────────────────────────────────────────
      } else if (data.type === "subagent_error") {
        const errorType: string = data.subagent_id || ""

        setSubagents((prev) => {
          const updated = new Map(prev)
          const sa = updated.get(errorType)
          if (sa) updated.set(errorType, { ...sa, status: "error" })
          return updated
        })

        setChatItems((prev) => {
          let lastRunningIdx = -1
          for (let i = 0; i < prev.length; i++) {
            const item = prev[i]
            if (
              item.kind === "subagent_activity" &&
              (item as ChatSubagentActivity).subagent_type === errorType &&
              (item as ChatSubagentActivity).status === "running"
            ) {
              lastRunningIdx = i
            }
          }
          if (lastRunningIdx === -1) return prev
          return prev.map((item, i) =>
            i === lastRunningIdx
              ? ({
                  ...item,
                  status: "error",
                  error: data.error || "Unknown error",
                  isExpanded: true,
                } as ChatSubagentActivity)
              : item,
          )
        })

        toast.error(`Sub-agent error: ${data.error}`)

      // ── tool_call ──────────────────────────────────────────────────────────
      } else if (data.type === "tool_call") {
        if (data.tool === "task") return
        const agentName: string = data.agent || ""
        console.log(`[tool_call] tool="${data.tool}" agent="${agentName}"`)
        const newCall: ActivityToolCall = {
          id: `${data.tool}-${Date.now()}`,
          tool: data.tool || "unknown",
          args: data.args || {},
          status: "running",
          result: null,
        }

        setChatItems((prev) => {
          console.log(`[tool_call] Searching for running activity with agent="${agentName}"`)
          console.log(`[tool_call] Current activities:`, prev.filter(i => i.kind === "subagent_activity").map(i => ({
            type: (i as ChatSubagentActivity).subagent_type,
            status: (i as ChatSubagentActivity).status
          })))
          let lastRunningIdx = -1
          for (let i = 0; i < prev.length; i++) {
            const item = prev[i]
            if (
              item.kind === "subagent_activity" &&
              (item as ChatSubagentActivity).status === "running" &&
              (!agentName || (item as ChatSubagentActivity).subagent_type === agentName)
            ) {
              lastRunningIdx = i
            }
          }
          if (lastRunningIdx === -1) {
            console.log(`[tool_call] NO MATCHING ACTIVITY FOUND - tool call dropped`)
            return prev
          }
          console.log(`[tool_call] Found activity at index ${lastRunningIdx}, adding tool call`)
          const activity = prev[lastRunningIdx] as ChatSubagentActivity
          return prev.map((item, i) =>
            i === lastRunningIdx
              ? ({ ...activity, toolCalls: [...activity.toolCalls, newCall] } as ChatSubagentActivity)
              : item,
          )
        })

      // ── tool_result ────────────────────────────────────────────────────────
      } else if (data.type === "tool_result") {
        if (data.tool === "task") return
        const toolName: string = data.tool || ""
        const agentName: string = data.agent || ""

        setChatItems((prev) => {
          const newItems = [...prev]
          for (let i = newItems.length - 1; i >= 0; i--) {
            const item = newItems[i]
            if (item.kind !== "subagent_activity") continue
            const act = item as ChatSubagentActivity
            if (agentName && act.subagent_type !== agentName) continue

            let lastRunningCallIdx = -1
            for (let j = 0; j < act.toolCalls.length; j++) {
              if (act.toolCalls[j].tool === toolName && act.toolCalls[j].status === "running") {
                lastRunningCallIdx = j
              }
            }
            if (lastRunningCallIdx !== -1) {
              const updatedCalls = act.toolCalls.map((c, ci) =>
                ci === lastRunningCallIdx
                  ? { ...c, status: "complete" as const, result: data.result || "" }
                  : c,
              )
              newItems[i] = { ...act, toolCalls: updatedCalls } as ChatSubagentActivity
              return newItems
            }
          }
          return prev
        })

      // ── todo_update ────────────────────────────────────────────────────────
      } else if (data.type === "todo_update") {
        const newTodos: Todo[] = data.todos || []
        const prevTodos = prevTodosRef.current

        // Detect newly completed todos → inject notification into chat
        const newlyCompleted = newTodos.filter(
          (t) =>
            t.status === "completed" &&
            !prevTodos.find((p) => p.id === t.id && p.status === "completed"),
        )
        if (newlyCompleted.length > 0) {
          setChatItems((prev) => [
            ...prev,
            ...newlyCompleted.map((t) => ({
              kind: "todo_complete" as const,
              id: `todo-complete-${t.id}-${Date.now()}`,
              task: t.task,
              timestamp: new Date(),
            })),
          ])
        }

        prevTodosRef.current = newTodos
        setTodos(newTodos)

      // ── question ───────────────────────────────────────────────────────────
      } else if (data.type === "question") {
        console.log("📋 QUESTION RECEIVED:", data)
        console.log("Setting questionModal.isOpen = true")
        setQuestionModal({
          isOpen: true,
          questionId: data.question_id || null,
          question: data.question || "",
          choices: data.choices || [],
          otherValue: "",
          threadId: data.thread_id || null,
        })
        console.log("questionModal state updated")

      // ── validation ─────────────────────────────────────────────────────────
      } else if (data.type === "validation") {
        if (data.passed) {
          toast.success(`Course is ready! Readiness: ${(data.readiness_score * 100).toFixed(0)}%`)
        } else {
          toast.error("Course needs fixes before publishing")
        }

      // ── error ──────────────────────────────────────────────────────────────
      } else if (data.type === "error") {
        toast.error(data.content)

      // ── stream_complete ────────────────────────────────────────────────────
      } else if (data.type === "stream_complete") {
        setIsLoading(false)
        setChatItems((prev) =>
          prev.map((item) =>
            item.kind === "message" && (item as ChatMessage).isStreaming
              ? ({ ...item, isStreaming: false } as ChatMessage)
              : item,
          ),
        )
        setCurrentAgent("")
        setIsAgentThinking(false)
      }
    }

    wsRef.current.onclose = () => {
      setIsConnected(false)
      wsRef.current = null
      if (!allowReconnectRef.current) return
      if (reconnectTimerRef.current) return
      const attempt = Math.min(reconnectAttemptsRef.current + 1, 6)
      reconnectAttemptsRef.current = attempt
      const delayMs = Math.min(1000 * 2 ** (attempt - 1), 10000)
      reconnectTimerRef.current = setTimeout(() => {
        reconnectTimerRef.current = null
        connectWebSocket(sid)
      }, delayMs)
    }

    wsRef.current.onerror = () => {
      setIsConnected(false)
    }
  }

  // ── Handlers ───────────────────────────────────────────────────────────────

  const handleToggleActivity = (id: string) => {
    setChatItems((prev) =>
      prev.map((item) =>
        item.kind === "subagent_activity" && (item as ChatSubagentActivity).id === id
          ? ({
              ...item,
              isExpanded: !(item as ChatSubagentActivity).isExpanded,
            } as ChatSubagentActivity)
          : item,
      ),
    )
  }

  const handleQuestionAnswer = (choice: string) => {
    if (!wsRef.current) return
    wsRef.current.send(
      JSON.stringify({
        type: "question_answer",
        thread_id: questionModal.threadId,
        answer: choice,
        answer_type: "choice",
      }),
    )
    setQuestionModal({ isOpen: false, questionId: null, question: "", choices: [], otherValue: "", threadId: null })
  }

  const handleOtherAnswer = () => {
    if (!wsRef.current || !questionModal.otherValue.trim()) {
      toast.error("Please enter your answer")
      return
    }
    wsRef.current.send(
      JSON.stringify({
        type: "question_answer",
        thread_id: questionModal.threadId,
        answer: questionModal.otherValue.trim(),
        answer_type: "other",
      }),
    )
    setQuestionModal({ isOpen: false, questionId: null, question: "", choices: [], otherValue: "", threadId: null })
  }

  const handleSendMessage = async () => {
    if (!inputMessage.trim() || !sessionId) return
    const userMessage: ChatMessage = {
      kind: "message",
      id: Date.now().toString(),
      role: "user",
      content: inputMessage,
      timestamp: new Date(),
    }
    setChatItems((prev) => [...prev, userMessage])
    setInputMessage("")
    setIsLoading(true)
    try {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(
          JSON.stringify({ type: "message", message: userMessage.content, creator_id: creatorId }),
        )
        return
      }
      const response = await constructorApi.chat(sessionId, userMessage.content)
      setChatItems((prev) => [
        ...prev,
        {
          kind: "message",
          id: `${Date.now()}_assistant`,
          role: "assistant",
          content: response.response || "I received your message.",
          timestamp: new Date(),
        } as ChatMessage,
      ])
      toast.warning("WebSocket was not connected. Used HTTP fallback.")
    } catch (error: any) {
      toast.error(error.response?.data?.detail || "Failed to send message")
    } finally {
      setIsLoading(false)
    }
  }

  const handleFileUpload = async (files: FileList) => {
    if (!sessionId || !courseId) {
      toast.error("Session not ready. Please wait...")
      return
    }
    const newFiles: UploadedFile[] = Array.from(files).map((file) => ({
      id: Date.now().toString() + Math.random(),
      name: file.name,
      size: file.size,
      type: file.type,
      status: "uploading" as const,
    }))
    setUploadedFiles((prev) => [...prev, ...newFiles])
    try {
      await constructorApi.uploadFiles(sessionId, courseId, Array.from(files))
      setUploadedFiles((prev) =>
        prev.map((f) =>
          newFiles.find((nf) => nf.name === f.name) ? { ...f, status: "processing" } : f,
        ),
      )
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "upload", file_ids: newFiles.map((f) => f.id) }))
      } else if (sessionId) {
        connectWebSocket(sessionId)
      }
      setTimeout(() => {
        setUploadedFiles((prev) =>
          prev.map((f) =>
            newFiles.find((nf) => nf.name === f.name) ? { ...f, status: "completed" } : f,
          ),
        )
      }, 3000)
      toast.success(`Uploaded ${files.length} file(s)`)
    } catch {
      toast.error("Failed to upload files")
      setUploadedFiles((prev) =>
        prev.map((f) =>
          newFiles.find((nf) => nf.name === f.name) ? { ...f, status: "error" } : f,
        ),
      )
    }
  }

  const handleLogout = () => {
    logout()
    router.push("/auth/login")
  }

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return bytes + " B"
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB"
    return (bytes / (1024 * 1024)).toFixed(1) + " MB"
  }

  const getFileIcon = (type: string) => {
    if (type.includes("pdf")) return <FileText className="w-4 h-4" />
    if (type.includes("video")) return <Video className="w-4 h-4" />
    return <File className="w-4 h-4" />
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  if (!isStoreHydrated) {
    return (
      <div className="min-h-screen flex items-center justify-center gradient-bg">
        <div className="text-center space-y-4">
          <Loader2 className="w-8 h-8 animate-spin mx-auto text-primary" />
          <p className="text-muted-foreground">Loading...</p>
        </div>
      </div>
    )
  }

  const completedTodos = todos.filter((t) => t.status === "completed").length

  return (
    <div className="min-h-screen flex flex-col gradient-bg">
      {/* Header */}
      <header className="border-b border-border/50 bg-card/50 backdrop-blur-xl sticky top-0 z-50">
        <div className="max-w-[1600px] mx-auto px-4 h-16 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary to-purple-600 flex items-center justify-center">
              <Zap className="w-5 h-5 text-white" />
            </div>
            <span className="font-semibold">Constructor</span>
          </Link>
          <div className="flex items-center gap-4">
            <Link href="/constructor/courses">
              <Button variant="ghost" size="sm">
                My Courses
              </Button>
            </Link>
            <Button variant="ghost" size="sm" onClick={handleLogout}>
              <LogOut className="w-4 h-4" />
            </Button>
          </div>
        </div>
      </header>

      {/* DEBUG: Question Modal State */}
      {questionModal.isOpen && (
        <div className="fixed top-20 left-1/2 transform -translate-x-1/2 bg-red-500 text-white px-8 py-4 text-2xl font-bold z-[10000] border-8 border-yellow-400">
          ⚠️ QUESTION MODAL IS OPEN! Question: {questionModal.question}
        </div>
      )}

      <div className="flex-1 px-4 py-6">
        <div className="max-w-[1600px] mx-auto grid lg:grid-cols-5 gap-4">

          {/* ── Left Sidebar: File Upload ──────────────────────────────────── */}
          <div className="lg:col-span-1">
            <div className="sticky top-24 space-y-4">
              <Card className="glass">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <Upload className="w-4 h-4" />
                    Upload Materials
                  </CardTitle>
                  <CardDescription className="text-xs">
                    PDFs, slides, videos, documents
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex items-center gap-1.5 text-xs">
                    <span
                      className={cn(
                        "w-1.5 h-1.5 rounded-full shrink-0",
                        isConnected ? "bg-green-400" : "bg-yellow-400 animate-pulse",
                      )}
                    />
                    <span className={isConnected ? "text-green-400" : "text-yellow-400"}>
                      {isConnected ? "Connected" : "Reconnecting..."}
                    </span>
                  </div>

                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full justify-start"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <Upload className="w-4 h-4 mr-2" />
                    Choose Files
                  </Button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    accept=".pdf,.ppt,.pptx,.docx,.txt,.mp4,.mov,.avi"
                    className="hidden"
                    onChange={(e) => e.target.files && handleFileUpload(e.target.files)}
                  />
                </CardContent>
              </Card>

              {/* Uploaded Files */}
              {uploadedFiles.length > 0 && (
                <Card className="glass">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-xs font-medium text-muted-foreground">
                      Uploaded Files
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {uploadedFiles.map((file) => (
                        <div
                          key={file.id}
                          className="flex items-center gap-2 p-2 rounded-lg bg-muted/30 text-xs"
                        >
                          {getFileIcon(file.type)}
                          <span className="flex-1 truncate">{file.name}</span>
                          <span className="text-muted-foreground shrink-0">
                            {formatFileSize(file.size)}
                          </span>
                          {file.status === "completed" && (
                            <CheckCircle2 className="w-3.5 h-3.5 text-green-500 shrink-0" />
                          )}
                          {(file.status === "processing" || file.status === "uploading") && (
                            <Loader2 className="w-3.5 h-3.5 animate-spin text-primary shrink-0" />
                          )}
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          </div>

          {/* ── Center: Chat + Timeline ────────────────────────────────────── */}
          <div className="lg:col-span-3">
            <Card className="min-h-[calc(100vh-13rem)] flex flex-col glass">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle>Course Constructor</CardTitle>
                    <CardDescription>Build your course with AI assistance</CardDescription>
                  </div>
                  {(isAgentThinking || currentAgent) && (
                    <div className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full bg-purple-500/10 border border-purple-500/20">
                      <span className="w-1.5 h-1.5 rounded-full bg-purple-400 animate-pulse" />
                      <span className="text-purple-300">{currentAgent || "Working"}</span>
                    </div>
                  )}
                </div>
              </CardHeader>

              <CardContent className="flex flex-col p-4 min-h-[inherit]">
                <div className="flex-1 space-y-4 mb-4 min-h-[200px]">
                  {chatItems.map((item) => {
                    // Regular message bubble
                    if (item.kind === "message") {
                      const msg = item as ChatMessage
                      return (
                        <div
                          key={msg.id}
                          className={cn(
                            "flex animate-fade-in",
                            msg.role === "user" ? "justify-end" : "justify-start",
                          )}
                        >
                          <div
                            className={cn(
                              "max-w-[80%] rounded-2xl px-4 py-3",
                              msg.role === "user"
                                ? "bg-primary text-primary-foreground rounded-br-sm"
                                : "bg-muted text-foreground rounded-bl-sm",
                            )}
                          >
                            {msg.role === "assistant" ? (
                              <ChatMarkdown content={msg.content} />
                            ) : (
                              <p className="whitespace-pre-wrap">{msg.content}</p>
                            )}
                            {msg.isStreaming && (
                              <span className="inline-block w-1 h-4 bg-current animate-pulse ml-1" />
                            )}
                          </div>
                        </div>
                      )
                    }

                    // Sub-agent activity timeline entry
                    if (item.kind === "subagent_activity") {
                      return (
                        <SubagentActivityEntry
                          key={(item as ChatSubagentActivity).id}
                          activity={item as ChatSubagentActivity}
                          onToggle={handleToggleActivity}
                        />
                      )
                    }

                    // Todo completion notification
                    if (item.kind === "todo_complete") {
                      const tc = item as ChatTodoComplete
                      return (
                        <div key={tc.id} className="flex justify-center animate-fade-in">
                          <div className="flex items-center gap-2 text-xs px-3 py-1.5 rounded-full bg-green-500/10 border border-green-500/20 text-green-400">
                            <CheckCircle2 className="w-3 h-3 shrink-0" />
                            <span>
                              Completed: <span className="font-medium">{tc.task}</span>
                            </span>
                          </div>
                        </div>
                      )
                    }

                    return null
                  })}

                  {/* Typing indicator (before first token arrives) */}
                  {isLoading && (
                    <div className="flex justify-start">
                      <div className="max-w-[80%] rounded-2xl px-4 py-3 bg-muted">
                        <div className="flex gap-1">
                          <span className="typing-dot" />
                          <span className="typing-dot" />
                          <span className="typing-dot" />
                        </div>
                      </div>
                    </div>
                  )}

                  <div ref={chatEndRef} />
                </div>

                {/* Input */}
                <div className="border-t border-border/50 pt-4">
                  {(() => {
                    const isGenerating =
                      isLoading ||
                      chatItems.some(
                        (item) => item.kind === "message" && (item as ChatMessage).isStreaming,
                      )
                    return (
                      <div className="flex gap-2">
                        <Textarea
                          ref={textareaRef}
                          placeholder="Tell me about your course..."
                          value={inputMessage}
                          onChange={(e) => setInputMessage(e.target.value)}
                          onKeyDown={(e) =>
                            e.key === "Enter" &&
                            !e.shiftKey &&
                            (e.preventDefault(), handleSendMessage())
                          }
                          className="flex-1 min-h-[44px] max-h-40 overflow-y-auto"
                        />
                        <Button
                          onClick={handleSendMessage}
                          disabled={!inputMessage.trim() || isGenerating}
                          size="icon"
                          className="button-press shrink-0 rounded-full"
                        >
                          {isGenerating ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                          ) : (
                            <ArrowUp className="w-4 h-4" />
                          )}
                        </Button>
                      </div>
                    )
                  })()}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* ── Right Sidebar: Todos + Agent Graph ────────────────────────── */}
          <div className="lg:col-span-1">
            <div className="sticky top-24 space-y-4 max-h-[calc(100vh-8rem)] overflow-y-auto pl-2">
              {/* Agent Tasks */}
              <Card className="glass">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-primary" />
                    Agent Tasks
                  </CardTitle>
                  <CardDescription className="text-xs">Main agent progress</CardDescription>
                </CardHeader>
                <CardContent className="space-y-2">
                  {todos.length === 0 ? (
                    <div className="text-center text-muted-foreground text-sm py-4">
                      <Activity className="w-4 h-4 mx-auto mb-2 opacity-50" />
                      Waiting for agent to start...
                    </div>
                  ) : (
                    <>
                      <div className="space-y-1.5 pb-2 border-b border-border/50">
                        <div className="flex justify-between text-xs">
                          <span className="text-muted-foreground">Progress</span>
                          <span className="font-mono">
                            {completedTodos}/{todos.length}
                          </span>
                        </div>
                        <Progress
                          value={(completedTodos / todos.length) * 100}
                          className="h-1.5"
                        />
                      </div>
                      <div className="space-y-2">
                        {todos.map((todo, idx) => (
                          <div
                            key={todo.id || idx}
                            className={cn(
                              "flex items-start gap-2 p-2 rounded-lg text-xs border transition-all",
                              todo.status === "completed"
                                ? "bg-green-500/10 border-green-500/20 opacity-60"
                                : "bg-muted/30 border-border/50",
                            )}
                          >
                            <div
                              className={cn(
                                "flex-shrink-0 mt-0.5",
                                todo.status === "completed"
                                  ? "text-green-500"
                                  : todo.status === "in_progress"
                                    ? "text-blue-500"
                                    : "text-muted-foreground",
                              )}
                            >
                              {todo.status === "completed" ? (
                                <CheckCircle2 className="w-3.5 h-3.5" />
                              ) : todo.status === "in_progress" ? (
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              ) : (
                                <Circle className="w-3.5 h-3.5" />
                              )}
                            </div>
                            <p
                              className={cn(
                                "text-xs font-medium",
                                todo.status === "completed"
                                  ? "line-through text-muted-foreground"
                                  : "",
                              )}
                            >
                              {todo.task}
                            </p>
                          </div>
                        ))}
                      </div>
                    </>
                  )}
                </CardContent>
              </Card>

              {/* Agent Hierarchy Graph */}
              <Card className="glass">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <Bot className="w-4 h-4 text-primary" />
                    Agent Graph
                  </CardTitle>
                  <CardDescription className="text-xs">Active agents</CardDescription>
                </CardHeader>
                <CardContent>
                  <AgentHierarchyGraph subagents={subagents} isMainActive={isMainActive} />
                </CardContent>
              </Card>
            </div>
          </div>

        </div>
      </div>

      {/* Question Modal - DEBUG VERSION */}
      {console.log("🎯 RENDERING QUESTION MODAL - isOpen:", questionModal.isOpen, "question:", questionModal.question)}
      <Dialog
        key={questionModal.questionId}
        open={questionModal.isOpen}
        onOpenChange={(open) => {
          console.log("📝 Dialog onOpenChange called with:", open)
          setQuestionModal((prev) => ({ ...prev, isOpen: open }))
        }}
      >
        <DialogContent className="sm:max-w-md" style={{ backgroundColor: "red", border: "10px solid yellow", zIndex: 9999 }}>
          <DialogHeader>
            <DialogTitle className="text-lg">Question</DialogTitle>
            <DialogDescription className="text-base text-foreground">
              {questionModal.question}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-4">
            {questionModal.choices.map((choice, index) => (
              <Button
                key={index}
                variant="outline"
                className="w-full justify-start h-auto py-3 px-4 text-left"
                onClick={() => handleQuestionAnswer(choice)}
              >
                <span className="flex items-center gap-3">
                  <span className="w-6 h-6 rounded-full bg-primary/10 flex items-center justify-center text-xs font-medium">
                    {index + 1}
                  </span>
                  <span>{choice}</span>
                </span>
              </Button>
            ))}
            <div className="space-y-2 pt-2 border-t">
              <Label className="text-sm text-muted-foreground">Other (type your answer):</Label>
              <div className="flex gap-2">
                <Input
                  placeholder="Type your custom answer..."
                  value={questionModal.otherValue}
                  onChange={(e) => setQuestionModal((prev) => ({ ...prev, otherValue: e.target.value }))}
                  onKeyDown={(e) => e.key === "Enter" && handleOtherAnswer()}
                  className="flex-1"
                />
                <Button
                  onClick={handleOtherAnswer}
                  disabled={!questionModal.otherValue.trim()}
                  size="sm"
                >
                  Send
                </Button>
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
