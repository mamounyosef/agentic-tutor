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
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import {
  Zap,
  Upload,
  Send,
  Loader2,
  FileText,
  Video,
  File,
  CheckCircle2,
  LogOut,
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

interface QuestionModal {
  isOpen: boolean
  questionId: string | null
  question: string
  choices: string[]
  otherValue: string
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
  const { creatorId, creatorToken, logout, _hasHydrated } = useAuthStore()
  const [messages, setMessages] = useState<Message[]>([])
  const [inputMessage, setInputMessage] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [isConnected, setIsConnected] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [courseId, setCourseId] = useState<number | null>(null)
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([])
  const [progress, setProgress] = useState(0)
  const [phase, setPhase] = useState("")
  const [isStoreHydrated, setIsStoreHydrated] = useState(false)
  const [currentAgent, setCurrentAgent] = useState<string>("")
  const [isSubagentWorking, setIsSubagentWorking] = useState<boolean>(false)
  const [isAgentThinking, setIsAgentThinking] = useState<boolean>(false)
  const [recentToolCalls, setRecentToolCalls] = useState<ToolCall[]>([])
  const [recentToolResults, setRecentToolResults] = useState<ToolResult[]>([])
  // New: Subagent tracking
  const [subagents, setSubagents] = useState<Map<string, Subagent>>(new Map())
  const [todos, setTodos] = useState<Todo[]>([])
  // Question modal state
  const [questionModal, setQuestionModal] = useState<{
    isOpen: boolean
    questionId: string | null
    question: string
    choices: string[]
    otherValue: string
  }>({
    isOpen: false,
    questionId: null,
    question: "",
    choices: [],
    otherValue: "",
  })
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const initRequestIdRef = useRef(0)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const allowReconnectRef = useRef(true)

  useEffect(() => {
    // Only redirect to login after store has hydrated from localStorage
    if (_hasHydrated && !creatorToken) {
      router.push("/auth/login")
      return
    }

    // Only initialize if we have a token and store has hydrated
    if (_hasHydrated && creatorToken) {
      initializeSession()
    }

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

  // Track store hydration state
  useEffect(() => {
    if (_hasHydrated) {
      setIsStoreHydrated(true)
    }
  }, [_hasHydrated])

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current
    if (!textarea) return

    const resize = () => {
      textarea.style.height = 'auto'
      textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`
    }

    resize()
    textarea.addEventListener('input', resize)
    return () => textarea.removeEventListener('input', resize)
  }, [inputMessage])

  const initializeSession = async () => {
    const requestId = ++initRequestIdRef.current
    try {
      const response = await constructorApi.startSession()
      if (requestId !== initRequestIdRef.current) return

      setSessionId(response.session_id)
      setCourseId(response.course_id)

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
        setIsAgentThinking(true)
      } else if (data.type === "agent_done_thinking") {
        // Agent done thinking - keep current agent for continuity
        setIsAgentThinking(false)
      } else if (data.type === "subagent_start") {
        // New subagent starting - use subagent_type as key to deduplicate
        const subagentType = data.subagent_type || "Unknown"
        const newSubagent: Subagent = {
          id: subagentType, // Use type as ID to prevent duplicates
          subagent_type: subagentType,
          description: data.description || "",
          status: "running",
          startedAt: new Date(),
          completedAt: null,
          result: null,
          error: null,
          toolCalls: [],
        }
        setSubagents((prev) => {
          // If subagent of this type already exists and is running, don't recreate it
          const existing = prev.get(subagentType)
          if (existing && existing.status === "running") {
            return prev // Already running, skip duplicate
          }
          return new Map(prev).set(subagentType, newSubagent)
        })
        setCurrentAgent(subagentType)
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
        // Skip internal 'task' tool (used for subagent delegation)
        if (data.tool === "task") return

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
        // Skip internal 'task' tool (used for subagent delegation)
        if (data.tool === "task") return

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
      } else if (data.type === "question") {
        // Structured question from agent - show as modal
        setQuestionModal({
          isOpen: true,
          questionId: data.question_id || null,
          question: data.question || "",
          choices: data.choices || [],
          otherValue: "",
        })
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
        setIsAgentThinking(false)
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

  const handleQuestionAnswer = (choice: string) => {
    if (!wsRef.current || !questionModal.questionId) return

    // Send the answer via WebSocket
    wsRef.current.send(JSON.stringify({
      type: "question_answer",
      question_id: questionModal.questionId,
      answer: choice,
      answer_type: "choice",
    }))

    // Close the modal
    setQuestionModal({
      isOpen: false,
      questionId: null,
      question: "",
      choices: [],
      otherValue: "",
    })
  }

  const handleOtherAnswer = () => {
    if (!wsRef.current || !questionModal.questionId || !questionModal.otherValue.trim()) {
      toast.error("Please enter your answer")
      return
    }

    // Send the answer via WebSocket
    wsRef.current.send(JSON.stringify({
      type: "question_answer",
      question_id: questionModal.questionId,
      answer: questionModal.otherValue.trim(),
      answer_type: "other",
    }))

    // Close the modal
    setQuestionModal({
      isOpen: false,
      questionId: null,
      question: "",
      choices: [],
      otherValue: "",
    })
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

  // Show loading while store hydrates from localStorage
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
              <Button variant="ghost" size="sm">My Courses</Button>
            </Link>
            <Button variant="ghost" size="sm" onClick={handleLogout}>
              <LogOut className="w-4 h-4" />
            </Button>
          </div>
        </div>
      </header>

      <div className="flex-1 px-4 py-6">
        <div className="max-w-[1600px] mx-auto grid lg:grid-cols-5 gap-4">
          {/* Left Sidebar - Session Progress */}
          <div className="lg:col-span-1">
            <div className="sticky top-24 space-y-4 max-h-[calc(100vh-8rem)] overflow-y-auto pr-2">
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
                  <ScrollArea className="h-20">
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
          </div>

          {/* Main Chat Area */}
          <div className="lg:col-span-3">
            <Card className="min-h-[calc(100vh-13rem)] flex flex-col glass">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle>Course Constructor</CardTitle>
                    <CardDescription>
                      Build your course with AI assistance
                    </CardDescription>
                  </div>
                  <div className="flex items-center gap-3">
                    {/* Agent working indicator */}
                    {(isAgentThinking || currentAgent) && (
                      <div className="flex items-center gap-1.5 text-xs px-2 py-1 rounded-full bg-purple-500/10 border border-purple-500/20">
                        <span className={cn(
                          "w-1.5 h-1.5 rounded-full",
                          isAgentThinking ? "bg-purple-500 animate-ping" : "bg-purple-500"
                        )} />
                        <span className="text-purple-300">
                          {currentAgent || "Working"}
                        </span>
                      </div>
                    )}
                    {/* Connection status */}
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-muted-foreground">
                        {isConnected ? "Online" : "Connecting..."}
                      </span>
                      <div
                        className={cn(
                          "w-2.5 h-2.5 rounded-full transition-colors duration-300",
                          isConnected
                            ? "bg-green-500 agent-alive-dot"
                            : "bg-yellow-500 animate-pulse"
                        )}
                      />
                    </div>
                  </div>
                </div>
              </CardHeader>

              <CardContent className="flex flex-col p-4 min-h-[inherit]">
                {/* Messages */}
                <div className="flex-1 space-y-6 mb-4 min-h-[200px]">
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
                  {isAgentThinking && !isLoading && currentAgent && (
                    <div className="flex justify-start animate-fade-in">
                      <div className="max-w-[80%] rounded-2xl px-4 py-3 bg-purple-500/10 border border-purple-500/20">
                        <div className="flex items-center gap-2 text-sm">
                          <Bot className="w-4 h-4 text-purple-500 animate-pulse" />
                          <span className="text-purple-300">
                            {currentAgent} is working...
                          </span>
                        </div>
                      </div>
                    </div>
                  )}
                  <div ref={messagesEndRef} />
                </div>

                {/* Input */}
                <div className="border-t border-border/50 pt-4">
                  <div className="flex gap-2">
                    <Textarea
                      ref={textareaRef}
                      placeholder="Tell me about your course..."
                      value={inputMessage}
                      onChange={(e) => setInputMessage(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), handleSendMessage())}
                      className="flex-1 min-h-[44px] max-h-40 overflow-y-auto"
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

          {/* Right Sidebar - TODO List */}
          <div className="lg:col-span-1">
            <div className="sticky top-24 space-y-4 max-h-[calc(100vh-8rem)] overflow-y-auto pl-2">
              {/* TODO List Card */}
              <Card className="glass">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-primary" />
                    Agent Tasks
                  </CardTitle>
                  <CardDescription className="text-xs">
                    Main agent progress tracking
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-2">
                  {todos.length === 0 ? (
                    <div className="text-center text-muted-foreground text-sm py-4">
                      <Activity className="w-4 h-4 mx-auto mb-2 opacity-50" />
                      Waiting for agent to start...
                    </div>
                  ) : (
                    <>
                      {/* Progress bar */}
                      <div className="space-y-1.5 pb-2 border-b border-border/50">
                        <div className="flex justify-between text-xs">
                          <span className="text-muted-foreground">Progress</span>
                          <span className="font-mono">
                            {todos.filter(t => t.status === "completed").length}/{todos.length}
                          </span>
                        </div>
                        <Progress
                          value={(todos.filter(t => t.status === "completed").length / todos.length) * 100}
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
                                : "bg-muted/30 border-border/50"
                            )}
                          >
                            <div className={cn(
                              "flex-shrink-0 mt-0.5",
                              todo.status === "completed"
                                ? "text-green-500"
                                : todo.status === "in_progress"
                                  ? "text-blue-500 animate-pulse"
                                  : "text-muted-foreground"
                            )}>
                              {todo.status === "completed" ? (
                                <CheckCircle2 className="w-3.5 h-3.5" />
                              ) : todo.status === "in_progress" ? (
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              ) : (
                                <Circle className="w-3.5 h-3.5" />
                              )}
                            </div>
                            <div className="flex-1 min-w-0">
                              <p className={cn(
                                "text-xs font-medium",
                                todo.status === "completed" ? "line-through text-muted-foreground" : ""
                              )}>
                                {todo.task}
                              </p>
                            </div>
                          </div>
                        ))}
                      </div>
                    </>
                  )}
                </CardContent>
              </Card>

              {/* Quick Status */}
              <Card className="glass">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-medium">Workflow Status</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="space-y-1">
                    <div className="flex justify-between text-xs">
                      <span className="text-muted-foreground">Messages</span>
                      <span className="font-mono">{messages.length}</span>
                    </div>
                    <div className="flex justify-between text-xs">
                      <span className="text-muted-foreground">Files</span>
                      <span className="font-mono">{uploadedFiles.length}</span>
                    </div>
                    <div className="flex justify-between text-xs">
                      <span className="text-muted-foreground">Subagents</span>
                      <span className="font-mono">{Array.from(subagents.values()).filter(s => s.status === "running").length} active</span>
                    </div>
                  </div>

                  {phase && (
                    <div className="pt-2 border-t border-border/50">
                      <div className="text-xs text-muted-foreground mb-1">Current Phase</div>
                      <div className="text-xs font-medium capitalize">{phase}</div>
                      {progress > 0 && (
                        <Progress value={progress} className="h-1 mt-2" />
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          </div>
        </div>
      </div>

      {/* Question Modal */}
      <Dialog open={questionModal.isOpen} onOpenChange={(open) => !open && setQuestionModal(prev => ({ ...prev, isOpen: false }))}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="text-lg">Question</DialogTitle>
            <DialogDescription className="text-base text-foreground">
              {questionModal.question}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-4">
            {/* Choice buttons */}
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

            {/* Other option with input */}
            <div className="space-y-2 pt-2 border-t">
              <Label className="text-sm text-muted-foreground">Other (type your answer):</Label>
              <div className="flex gap-2">
                <Input
                  placeholder="Type your custom answer..."
                  value={questionModal.otherValue}
                  onChange={(e) => setQuestionModal(prev => ({ ...prev, otherValue: e.target.value }))}
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
