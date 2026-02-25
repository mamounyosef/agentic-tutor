"use client"

import { useState, useEffect, useRef } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { Progress } from "@/components/ui/progress"
import {
  Zap,
  Plus,
  Upload,
  X,
  Send,
  Loader2,
  FileText,
  Video,
  File,
  CheckCircle2,
  LogOut,
  Menu,
  Settings,
  BookOpen,
  Bot,
  Wrench,
  ChevronRight,
  Activity,
  Circle,
  Clock,
} from "lucide-react"
import { useAuthStore } from "@/lib/store"
import { constructorApi } from "@/lib/api"
import { cn } from "@/lib/utils"
import { ChatMarkdown } from "@/components/chat-markdown"

interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  timestamp: Date
  isStreaming?: boolean
  streamId?: string
}

interface UploadedFile {
  id: string
  name: string
  size: number
  type: string
  status: "uploading" | "processing" | "completed" | "error"
}

interface Subagent {
  id: string
  subagent_type: string
  description: string
  status: "pending" | "running" | "complete" | "error"
  startedAt: Date | null
  completedAt: Date | null
  result: string | null
  error: string | null
  toolCalls: ToolCall[]
}

interface Todo {
  id: string
  task: string
  status: "pending" | "in_progress" | "completed"
}

interface ToolCall {
  tool: string
  args: string
  agent: string
  timestamp: Date
  result?: string
  isRunning?: boolean
}

interface ToolResult {
  tool: string
  result: string
  agent: string
  timestamp: Date
}

// Subagent Card Component
function SubagentCard({ subagent }: { subagent: Subagent }) {
  const getStatusIcon = () => {
    switch (subagent.status) {
      case "pending":
        return <Clock className="w-3 h-3 text-yellow-500" />
      case "running":
        return <Loader2 className="w-3 h-3 animate-spin text-blue-500" />
      case "complete":
        return <CheckCircle2 className="w-3 h-3 text-green-500" />
      case "error":
        return <Circle className="w-3 h-3 text-red-500 fill-current" />
      default:
        return <Circle className="w-3 h-3 text-gray-500" />
    }
  }

  const getStatusText = () => {
    switch (subagent.status) {
      case "pending": return "Starting..."
      case "running": return "Working..."
      case "complete": return "Complete"
      case "error": return "Error"
      default: return ""
    }
  }

  const getSubagentLabel = (type: string) => {
    // Format subagent type for display
    return type
      .replace(/_/g, " ")
      .replace(/-/g, " ")
      .split(" ")
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(" ")
  }

  return (
    <div className={cn(
      "border rounded-lg p-3 text-xs",
      subagent.status === "running" && "border-blue-500/30 bg-blue-500/5",
      subagent.status === "complete" && "border-green-500/30 bg-green-500/5",
      subagent.status === "error" && "border-red-500/30 bg-red-500/5",
    )}>
      {/* Header */}
      <div className="flex items-center gap-2 mb-2">
        {getStatusIcon()}
        <span className="font-medium">{getSubagentLabel(subagent.subagent_type)}</span>
        <span className={cn(
          "text-xs",
          subagent.status === "running" && "text-blue-400",
          subagent.status === "complete" && "text-green-400",
          subagent.status === "error" && "text-red-400",
        )}>
          {getStatusText()}
        </span>
      </div>

      {/* Description */}
      {subagent.description && (
        <p className="text-muted-foreground text-xs mb-2 line-clamp-2">
          {subagent.description}
        </p>
      )}

      {/* Tool calls */}
      {subagent.toolCalls.length > 0 && (
        <div className="space-y-1 mt-2">
          <div className="text-muted-foreground text-xs">Tools used:</div>
          {subagent.toolCalls.slice(-3).map((call, idx) => (
            <div key={idx} className="flex items-center gap-1 text-xs">
              <Wrench className="w-3 h-3 text-muted-foreground" />
              <span className="font-mono truncate">{call.tool}</span>
            </div>
          ))}
        </div>
      )}

      {/* Result preview */}
      {subagent.result && (
        <div className="mt-2 p-2 bg-green-500/10 border border-green-500/20 rounded">
          <div className="text-xs text-green-300 line-clamp-3">
            {subagent.result.slice(0, 200)}
            {subagent.result.length > 200 && "..."}
          </div>
        </div>
      )}

      {/* Error */}
      {subagent.error && (
        <div className="mt-2 p-2 bg-red-500/10 border border-red-500/20 rounded">
          <div className="text-xs text-red-300">
            {subagent.error}
          </div>
        </div>
      )}
    </div>
  )
}

export default function ConstructorDashboard() {
  const router = useRouter()
  const { creatorId, creatorToken, logout } = useAuthStore()
  const [messages, setMessages] = useState<Message[]>([])
  const [inputMessage, setInputMessage] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [isConnected, setIsConnected] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([])
  const [progress, setProgress] = useState(0)
  const [phase, setPhase] = useState("")
  const [currentAgent, setCurrentAgent] = useState<string>("")
  const [isSubagentWorking, setIsSubagentWorking] = useState<boolean>(false)
  const [recentToolCalls, setRecentToolCalls] = useState<ToolCall[]>([])
  const [recentToolResults, setRecentToolResults] = useState<ToolResult[]>([])
  // New: Subagent tracking
  const [subagents, setSubagents] = useState<Map<string, Subagent>>(new Map())
  const [todos, setTodos] = useState<Todo[]>([])
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const initRequestIdRef = useRef(0)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const allowReconnectRef = useRef(true)

  useEffect(() => {
    if (!creatorToken) {
      router.push("/auth/login")
      return
    }

    // Initialize session
    initializeSession()

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
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  // Auto-clear completed tool results after 5 seconds
  useEffect(() => {
    if (recentToolResults.length > 0) {
      const timer = setTimeout(() => {
        setRecentToolResults([])
      }, 5000)
      return () => clearTimeout(timer)
    }
  }, [recentToolResults])

  const initializeSession = async () => {
    const requestId = ++initRequestIdRef.current
    try {
      const response = await constructorApi.startSession()
      if (requestId !== initRequestIdRef.current) return

      setSessionId(response.session_id)

      // Add welcome message
      setMessages([{
        id: "welcome",
        role: "assistant",
        content: response.message || "Hello! I'm your Course Constructor Assistant. Let's build a course together!",
        timestamp: new Date(),
      }])

      // Connect WebSocket for streaming
      connectWebSocket(response.session_id)
    } catch (error: any) {
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
        // Guard against accidental ws through Next dev proxy on :3000.
        if (
          url.port === "3000" &&
          (url.hostname === "localhost" || url.hostname === "127.0.0.1")
        ) {
          return `${wsProtocol}://localhost:8000`
        }
        const protocol = url.protocol === "https:" ? "wss" : "ws"
        return `${protocol}://${url.host}`
      } catch {
        // Fall through to localhost backend default.
      }
    }

    return `${wsProtocol}://${window.location.hostname}:8000`
  }

  const connectWebSocket = (sessionId: string) => {
    if (wsRef.current && (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING)) {
      return
    }

    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }

    const wsBase = resolveWebSocketBase()
    const wsUrl = `${wsBase}/api/v1/constructor/session/ws/${sessionId}`

    wsRef.current = new WebSocket(wsUrl)

    wsRef.current.onopen = () => {
      setIsConnected(true)
      reconnectAttemptsRef.current = 0
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
    }

    wsRef.current.onmessage = (event) => {
      const data = JSON.parse(event.data)

      if (data.type === "token") {
        const isFirst = Boolean(data.metadata?.is_first)
        const isLast = Boolean(data.metadata?.is_last)
        const streamId = String(data.metadata?.stream_id || "")

        // Streaming token
        setMessages((prev) => {
          if (isFirst) {
            const last = prev[prev.length - 1]
            if (
              last?.role === "assistant" &&
              !last.isStreaming &&
              streamId &&
              last.streamId === streamId
            ) {
              return prev
            }
            return [
              ...prev,
              {
                id: Date.now().toString(),
                role: "assistant",
                content: data.content,
                timestamp: new Date(),
                isStreaming: !isLast,
                streamId,
              },
            ]
          }

          const idx = [...prev].reverse().findIndex(
            (m) =>
              m.role === "assistant" &&
              m.isStreaming &&
              (!!streamId ? m.streamId === streamId : true)
          )
          if (idx !== -1) {
            const realIdx = prev.length - 1 - idx
            const current = prev[realIdx]
            return prev.map((m, i) =>
              i === realIdx
                ? {
                    ...current,
                    content: current.content + data.content,
                    isStreaming: !isLast,
                    streamId: current.streamId || streamId,
                  }
                : m
            )
          }

          return [
            ...prev,
            {
              id: Date.now().toString(),
              role: "assistant",
              content: data.content,
              timestamp: new Date(),
              isStreaming: !isLast,
              streamId,
            },
          ]
        })
      } else if (data.type === "status") {
        // Handle status updates from the new streaming format
        if (data.status) {
          setPhase(data.status)
        }
        if (data.metadata?.phase) {
          setPhase(data.metadata.phase)
        }
        if (data.metadata?.progress !== undefined) {
          setProgress(data.metadata.progress * 100)
        }
      } else if (data.type === "agent_change") {
        // Agent changed - update current agent display
        setCurrentAgent(data.agent || "Unknown")
        setIsSubagentWorking(data.is_subagent || false)
      } else if (data.type === "agent_thinking") {
        // Agent is thinking
        setCurrentAgent(data.agent || "Unknown")
      } else if (data.type === "agent_done_thinking") {
        // Agent done thinking - keep current agent for continuity
      } else if (data.type === "subagent_start") {
        // New subagent starting
        const newSubagent: Subagent = {
          id: data.subagent_id || Date.now().toString(),
          subagent_type: data.subagent_type || "Unknown",
          description: data.description || "",
          status: "running",
          startedAt: new Date(),
          completedAt: null,
          result: null,
          error: null,
          toolCalls: [],
        }
        setSubagents((prev) => new Map(prev).set(newSubagent.id, newSubagent))
        setCurrentAgent(data.subagent_type || "Unknown")
        setIsSubagentWorking(true)
      } else if (data.type === "subagent_complete") {
        // Subagent completed
        setSubagents((prev) => {
          const updated = new Map(prev)
          for (const [id, subagent] of updated) {
            if (id === data.subagent_id || subagent.subagent_type === data.subagent_id) {
              updated.set(id, {
                ...subagent,
                status: "complete",
                completedAt: new Date(),
                result: data.result || null,
              })
            }
          }
          // Check if any subagents still running
          const stillRunning = Array.from(updated.values()).filter(s => s.status === "running")
          if (stillRunning.length === 0) {
            setIsSubagentWorking(false)
            setCurrentAgent("")
          }
          return updated
        })
      } else if (data.type === "subagent_error") {
        // Subagent error
        setSubagents((prev) => {
          const updated = new Map(prev)
          for (const [id, subagent] of updated) {
            if (id === data.subagent_id || subagent.subagent_type === data.subagent_id) {
              updated.set(id, {
                ...subagent,
                status: "error",
                completedAt: new Date(),
                error: data.error || "Unknown error",
              })
            }
          }
          // Check if any subagents still running
          const stillRunning = Array.from(updated.values()).filter(s => s.status === "running")
          if (stillRunning.length === 0) {
            setIsSubagentWorking(false)
            setCurrentAgent("")
          }
          return updated
        })
        toast.error(`Subagent error: ${data.error}`)
      } else if (data.type === "tool_call") {
        // Tool is being called
        const newToolCall: ToolCall = {
          tool: data.tool || "unknown",
          args: JSON.stringify(data.args || {}),
          agent: data.agent || "Unknown",
          timestamp: new Date(),
          isRunning: true,
        }
        setRecentToolCalls((prev) => [...prev.slice(-4), newToolCall]) // Keep last 5
        // Clear from results when tool is called
        setRecentToolResults((prev) => prev.filter(r => r.tool !== data.tool))
        // Add to subagent's tool calls if applicable
        if (data.subagent_id) {
          setSubagents((prev) => {
            const updated = new Map(prev)
            const subagent = updated.get(data.subagent_id)
            if (subagent) {
              updated.set(data.subagent_id, {
                ...subagent,
                toolCalls: [...subagent.toolCalls, newToolCall],
              })
            }
            return updated
          })
        }
      } else if (data.type === "tool_result") {
        // Tool completed
        const newToolResult: ToolResult = {
          tool: data.tool || "unknown",
          result: data.result || "",
          agent: data.agent || "Unknown",
          timestamp: new Date(),
        }
        setRecentToolResults((prev) => [...prev.slice(-2), newToolResult]) // Keep last 3
        // Remove from pending calls
        setRecentToolCalls((prev) => prev.filter(c => c.tool !== data.tool))
      } else if (data.type === "todo_update") {
        // Todo list update
        setTodos(data.todos || [])
      } else if (data.type === "validation") {
        // Validation complete
        if (data.passed) {
          toast.success(`Course is ready! Readiness: ${(data.readiness_score * 100).toFixed(0)}%`)
        } else {
          toast.error("Course needs fixes before publishing")
        }
        setProgress(data.readiness_score * 100)
      } else if (data.type === "error") {
        toast.error(data.content)
      } else if (data.type === "stream_complete") {
        // Stream complete - mark any streaming messages as complete
        setMessages((prev) =>
          prev.map((m) =>
            m.isStreaming ? { ...m, isStreaming: false } : m
          )
        )
        // Clear current agent
        setCurrentAgent("")
        setIsSubagentWorking(false)
        // Clear completed subagents after a delay
        setTimeout(() => {
          setSubagents((prev) => {
            const updated = new Map()
            // Keep only recently completed subagents (last 2)
            const completed = Array.from(prev.values())
              .filter(s => s.status === "complete" || s.status === "error")
              .slice(-2)
            completed.forEach(s => updated.set(s.id, s))
            return updated
          })
        }, 5000)
      }
    }

    wsRef.current.onclose = () => {
      setIsConnected(false)
      wsRef.current = null
      if (!allowReconnectRef.current) return
      if (reconnectTimerRef.current) return

      const attempt = Math.min(reconnectAttemptsRef.current + 1, 6)
      reconnectAttemptsRef.current = attempt
      const delayMs = Math.min(1000 * (2 ** (attempt - 1)), 10000)

      reconnectTimerRef.current = setTimeout(() => {
        reconnectTimerRef.current = null
        connectWebSocket(sessionId)
      }, delayMs)
    }

    wsRef.current.onerror = () => {
      setIsConnected(false)
      // onclose will schedule reconnect; keep this quiet to avoid toast spam.
    }
  }

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }

  const handleSendMessage = async () => {
    if (!inputMessage.trim() || !sessionId) return

    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: inputMessage,
      timestamp: new Date(),
    }

    setMessages((prev) => [...prev, userMessage])
    setInputMessage("")
    setIsLoading(true)

    try {
      // Preferred path: WebSocket streaming
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({
          type: "message",
          message: userMessage.content,
          creator_id: creatorId,
        }))
        return
      }

      // Fallback path: HTTP chat when WS is unavailable
      const response = await constructorApi.chat(sessionId, userMessage.content)
      setMessages((prev) => [
        ...prev,
        {
          id: `${Date.now()}_assistant`,
          role: "assistant",
          content: response.response || "I received your message.",
          timestamp: new Date(),
        },
      ])
      toast.warning("WebSocket was not connected. Used HTTP fallback.")
    } catch (error: any) {
      toast.error(error.response?.data?.detail || "Failed to send message")
    } finally {
      setIsLoading(false)
    }
  }

  const handleFileUpload = async (files: FileList) => {
    if (!sessionId) return

    const newFiles: UploadedFile[] = Array.from(files).map((file) => ({
      id: Date.now().toString() + Math.random(),
      name: file.name,
      size: file.size,
      type: file.type,
      status: "uploading" as const,
    }))

    setUploadedFiles((prev) => [...prev, ...newFiles])

    try {
      await constructorApi.uploadFiles(sessionId, Array.from(files))

      // Update file statuses
      setUploadedFiles((prev) =>
        prev.map((f) => {
          if (newFiles.find((nf) => nf.name === f.name)) {
            return { ...f, status: "processing" }
          }
          return f
        })
      )

      // Notify WebSocket
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({
          type: "upload",
          file_ids: newFiles.map((f) => f.id),
        }))
      } else if (sessionId) {
        connectWebSocket(sessionId)
      }

      // Simulate processing completion
      setTimeout(() => {
        setUploadedFiles((prev) =>
          prev.map((f) => {
            if (newFiles.find((nf) => nf.name === f.name)) {
              return { ...f, status: "completed" }
            }
            return f
          })
        )
      }, 3000)

      toast.success(`Uploaded ${files.length} file(s)`)
    } catch (error) {
      toast.error("Failed to upload files")
      setUploadedFiles((prev) =>
        prev.map((f) => {
          if (newFiles.find((nf) => nf.name === f.name)) {
            return { ...f, status: "error" }
          }
          return f
        })
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

  return (
    <div className="min-h-screen flex flex-col gradient-bg">
      {/* Header */}
      <header className="border-b border-border/50 bg-card/50 backdrop-blur-xl sticky top-0 z-50">
        <div className="container mx-auto px-4 h-16 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary to-purple-600 flex items-center justify-center">
              <Zap className="w-5 h-5 text-white" />
            </div>
            <span className="font-semibold">Constructor</span>
          </Link>

          <div className="flex items-center gap-4">
            <Link href="/constructor/courses">
              <Button variant="ghost" size="sm">My Courses</Button>
            </Link>
            <Button variant="ghost" size="sm" onClick={handleLogout}>
              <LogOut className="w-4 h-4" />
            </Button>
          </div>
        </div>
      </header>

      <div className="flex-1 container mx-auto px-4 py-6">
        <div className="grid lg:grid-cols-4 gap-6 h-[calc(100vh-120px)]">
          {/* Sidebar */}
          <div className="lg:col-span-1 space-y-4">
            {/* Session Status Card */}
            <Card className="glass">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium">Session Progress</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Status</span>
                    <span className={cn(
                      "flex items-center gap-1.5",
                      isConnected ? "text-green-500" : "text-yellow-500"
                    )}>
                      <span className="connection-dot connected" />
                      {isConnected ? "Connected" : "Reconnecting..."}
                    </span>
                  </div>
                  {phase && (
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Phase</span>
                      <span className="capitalize">{phase}</span>
                    </div>
                  )}
                </div>

                {progress > 0 && (
                  <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Completion</span>
                      <span>{progress.toFixed(0)}%</span>
                    </div>
                    <Progress value={progress} className="h-2" />
                  </div>
                )}

                {/* Current Agent Display */}
                {currentAgent && (
                  <div className="space-y-2">
                    <div className="flex items-center gap-2 text-sm">
                      <Bot className={cn(
                        "w-4 h-4",
                        isSubagentWorking ? "text-purple-500" : "text-primary"
                      )} />
                      <span className="text-muted-foreground">Working:</span>
                    </div>
                    <div className={cn(
                      "text-sm font-medium px-2 py-1.5 rounded-md",
                      isSubagentWorking
                        ? "bg-purple-500/20 text-purple-300 border border-purple-500/30"
                        : "bg-primary/20 text-primary border border-primary/30"
                    )}>
                      {currentAgent}
                    </div>
                  </div>
                )}

                {/* Recent Tool Calls */}
                {recentToolCalls.length > 0 && (
                  <div className="space-y-2">
                    <div className="flex items-center gap-2 text-sm">
                      <Wrench className="w-4 h-4 text-yellow-500" />
                      <span className="text-muted-foreground">Running Tools:</span>
                    </div>
                    <div className="space-y-1.5">
                      {recentToolCalls.map((call, idx) => (
                        <div
                          key={`${call.tool}-${idx}`}
                          className="flex items-center gap-2 text-xs bg-yellow-500/10 border border-yellow-500/20 rounded px-2 py-1"
                        >
                          <Loader2 className="w-3 h-3 animate-spin text-yellow-500" />
                          <span className="font-mono truncate">{call.tool}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Recent Tool Results */}
                {recentToolResults.length > 0 && (
                  <div className="space-y-2">
                    <div className="flex items-center gap-2 text-sm">
                      <CheckCircle2 className="w-4 h-4 text-green-500" />
                      <span className="text-muted-foreground">Completed:</span>
                    </div>
                    <div className="space-y-1.5">
                      {recentToolResults.map((result, idx) => (
                        <div
                          key={`${result.tool}-${idx}`}
                          className="flex items-center gap-2 text-xs bg-green-500/10 border border-green-500/20 rounded px-2 py-1"
                        >
                          <ChevronRight className="w-3 h-3 text-green-500" />
                          <span className="font-mono truncate">{result.tool}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Active Subagents */}
                {Array.from(subagents.values()).filter(s => s.status === "running" || s.status === "pending").length > 0 && (
                  <div className="space-y-2">
                    <div className="flex items-center gap-2 text-sm">
                      <Bot className="w-4 h-4 text-purple-500" />
                      <span className="text-muted-foreground">Active Subagents:</span>
                    </div>
                    <div className="space-y-2 max-h-64 overflow-y-auto">
                      {Array.from(subagents.values())
                        .filter(s => s.status === "running" || s.status === "pending")
                        .map((subagent) => (
                          <SubagentCard key={subagent.id} subagent={subagent} />
                        ))}
                    </div>
                  </div>
                )}

                {/* Completed Subagents (show last 2) */}
                {Array.from(subagents.values()).filter(s => s.status === "complete" || s.status === "error").length > 0 && (
                  <div className="space-y-2">
                    <Separator />
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <CheckCircle2 className="w-4 h-4" />
                      <span>Recent Activity</span>
                    </div>
                    <div className="space-y-2 max-h-40 overflow-y-auto">
                      {Array.from(subagents.values())
                        .filter(s => s.status === "complete" || s.status === "error")
                        .slice(-2)
                        .reverse()
                        .map((subagent) => (
                          <div
                            key={subagent.id}
                            className={cn(
                              "flex items-center gap-2 text-xs px-2 py-1 rounded",
                              subagent.status === "complete"
                                ? "bg-green-500/10 text-green-400"
                                : "bg-red-500/10 text-red-400"
                            )}
                          >
                            <CheckCircle2 className="w-3 h-3" />
                            <span>{subagent.subagent_type.replace(/_/g, " ")}</span>
                          </div>
                        ))}
                    </div>
                  </div>
                )}

                <Separator />

                {/* File Upload */}
                <div className="space-y-3">
                  <Label>Upload Materials</Label>
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full justify-start"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <Upload className="w-4 h-4 mr-2" />
                    Upload Files
                  </Button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    accept=".pdf,.ppt,.pptx,.docx,.txt,.mp4,.mov,.avi"
                    className="hidden"
                    onChange={(e) => e.target.files && handleFileUpload(e.target.files)}
                  />
                  <p className="text-xs text-muted-foreground">
                    PDFs, PPTs, Videos supported
                  </p>
                </div>
              </CardContent>
            </Card>

            {/* Uploaded Files */}
            {uploadedFiles.length > 0 && (
              <Card className="glass">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-medium">Uploaded Files</CardTitle>
                </CardHeader>
                <CardContent>
                  <ScrollArea className="h-40">
                    <div className="space-y-2">
                      {uploadedFiles.map((file) => (
                        <div
                          key={file.id}
                          className="flex items-center gap-2 p-2 rounded-lg bg-muted/30 text-sm"
                        >
                          {getFileIcon(file.type)}
                          <span className="flex-1 truncate">{file.name}</span>
                          <span className="text-xs text-muted-foreground">
                            {formatFileSize(file.size)}
                          </span>
                          {file.status === "completed" && (
                            <CheckCircle2 className="w-4 h-4 text-green-500" />
                          )}
                          {file.status === "processing" && (
                            <Loader2 className="w-4 h-4 animate-spin text-primary" />
                          )}
                        </div>
                      ))}
                    </div>
                  </ScrollArea>
                </CardContent>
              </Card>
            )}
          </div>

          {/* Main Chat Area */}
          <div className="lg:col-span-3">
            <Card className="h-full flex flex-col glass">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle>Course Constructor</CardTitle>
                    <CardDescription>
                      Build your course with AI assistance
                    </CardDescription>
                  </div>
                </div>
              </CardHeader>

              <CardContent className="flex-1 flex flex-col p-0">
                {/* Messages */}
                <ScrollArea className="flex-1 p-4">
                  <div className="space-y-6">
                    {messages.map((message) => (
                      <div
                        key={message.id}
                        className={cn(
                          "flex animate-fade-in",
                          message.role === "user" ? "justify-end" : "justify-start"
                        )}
                      >
                        <div
                          className={cn(
                            "max-w-[80%] rounded-2xl px-4 py-3",
                            message.role === "user"
                              ? "bg-primary text-primary-foreground rounded-br-sm"
                              : "bg-muted text-foreground rounded-bl-sm"
                          )}
                        >
                          {message.role === "assistant" ? (
                            <ChatMarkdown content={message.content} />
                          ) : (
                            <p className="whitespace-pre-wrap">{message.content}</p>
                          )}
                          {message.isStreaming && (
                            <span className="inline-block w-1 h-4 bg-current animate-pulse ml-1" />
                          )}
                        </div>
                      </div>
                    ))}
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
                  </div>
                  <div ref={messagesEndRef} />
                </ScrollArea>

                {/* Input */}
                <div className="p-4 border-t border-border/50">
                  <div className="flex gap-2">
                    <Textarea
                      placeholder="Tell me about your course..."
                      value={inputMessage}
                      onChange={(e) => setInputMessage(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), handleSendMessage())}
                      className="flex-1 min-h-[44px] max-h-40 resize-y"
                    />
                    <Button
                      onClick={handleSendMessage}
                      disabled={!inputMessage.trim() || isLoading}
                      size="icon"
                      className="button-press shrink-0"
                    >
                      <Send className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  )
}
