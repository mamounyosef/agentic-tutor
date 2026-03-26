"use client"

import { useState, useEffect, useRef } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Progress } from "@/components/ui/progress"
import { Badge } from "@/components/ui/badge"
import {
  BookOpen,
  Send,
  Loader2,
  LogOut,
  Home,
  TrendingUp,
  MessageSquare,
  Target,
  Award,
  ChevronRight,
  Sparkles,
  Menu,
  X,
  ChevronDown,
  ChevronUp,
  Copy,
  Check,
  Brain,
} from "lucide-react"
import { useAuthStore } from "@/lib/store"
import { tutorApi } from "@/lib/api"
import { cn } from "@/lib/utils"
import { ChatMarkdown } from "@/components/chat-markdown"

interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  timestamp: Date | string
  isStreaming?: boolean
}

interface Topic {
  id: number
  title: string
  mastery: number
}

interface QuizQuestion {
  question_id: number
  question_text: string
  question_type: string
  options?: { text: string; value: string }[]
}

export default function StudentLearnPage({ params }: { params: { courseId: string } }) {
  console.log("🚀 StudentLearnPage RENDERING - Component is loaded!")
  const router = useRouter()
  const { studentToken, studentId, logout, _hasHydrated } = useAuthStore()
  const courseId = parseInt(params.courseId)

  const [messages, setMessages] = useState<Message[]>([])
  const [inputMessage, setInputMessage] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [isConnected, setIsConnected] = useState(false)
  const [isStoreHydrated, setIsStoreHydrated] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [courseTitle, setCourseTitle] = useState("")
  const [topics, setTopics] = useState<Topic[]>([])
  const [currentTopic, setCurrentTopic] = useState<string>("")
  const [masteryScore, setMasteryScore] = useState(0)
  const [activeQuiz, setActiveQuiz] = useState<QuizQuestion | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [quizCollapsed, setQuizCollapsed] = useState(false)
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null)
  const [agentStatus, setAgentStatus] = useState<"idle" | "thinking" | "typing">("idle")
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const initRequestIdRef = useRef(0)

  useEffect(() => {
    // Only redirect to login after store has hydrated from localStorage
    if (_hasHydrated && !studentToken) {
      router.push("/auth/login")
      return
    }

    // Only initialize if we have a token and store has hydrated
    if (_hasHydrated && studentToken) {
      initializeSession()
      loadCourseDetails()
    }

    return () => {
      initRequestIdRef.current += 1
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [_hasHydrated, studentToken])

  // Track store hydration state
  useEffect(() => {
    if (_hasHydrated) {
      setIsStoreHydrated(true)
    }
  }, [_hasHydrated])

  useEffect(() => {
    scrollToBottom()
  }, [messages])

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

  // Auto-expand quiz when new question arrives
  useEffect(() => {
    if (activeQuiz) {
      setQuizCollapsed(false)
    }
  }, [activeQuiz])

  // Update agent status based on activity
  useEffect(() => {
    const lastMessage = messages[messages.length - 1]
    if (lastMessage?.isStreaming) {
      setAgentStatus("typing")
    } else if (isLoading) {
      setAgentStatus("thinking")
    } else {
      setAgentStatus("idle")
    }
  }, [isLoading, messages])

  const initializeSession = async () => {
    const requestId = ++initRequestIdRef.current
    try {
      const response = await tutorApi.startSession(courseId)
      if (requestId !== initRequestIdRef.current) return

      setSessionId(response.session_id)

      // Add welcome message
      setMessages([{
        id: "welcome",
        role: "assistant",
        content: response.message || "Hello! Let's learn together.",
        timestamp: new Date(),
      }])

      // Set initial mastery snapshot
      if (response.mastery_snapshot) {
        const topicList = Object.entries(response.mastery_snapshot).map(([id, score]) => ({
          id: parseInt(id),
          title: `Topic ${id}`,
          mastery: score as number,
        }))
        setTopics(topicList)
      }

      // Connect WebSocket
      connectWebSocket(response.session_id)
    } catch (error: any) {
      if (requestId !== initRequestIdRef.current) return
      toast.error(error.response?.data?.detail || "Failed to start session")
    }
  }

  const loadCourseDetails = async () => {
    try {
      const details = await tutorApi.getCourseDetails(courseId)
      setCourseTitle(details.title)
    } catch (error) {
      toast.error("Failed to load course details")
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
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }

    const wsBase = resolveWebSocketBase()
    const wsUrl = `${wsBase}/api/v1/tutor/session/ws/${sessionId}`

    wsRef.current = new WebSocket(wsUrl)

    wsRef.current.onopen = () => {
      setIsConnected(true)
    }

    wsRef.current.onmessage = (event) => {
      const data = JSON.parse(event.data)
      console.log("🔔 WebSocket message received:", data.type, data)

      if (data.type === "token") {
        const isFirst = Boolean(data.metadata?.is_first)
        const isLast = Boolean(data.metadata?.is_last)

        // Clear loading state when streaming completes
        if (isLast) {
          setIsLoading(false)
        }

        // Streaming token
        setMessages((prev) => {
          if (isFirst) {
            return [
              ...prev,
              {
                id: Date.now().toString(),
                role: "assistant",
                content: data.content,
                timestamp: new Date(),
                isStreaming: !isLast,
              },
            ]
          }

          const lastMessage = prev[prev.length - 1]
          if (lastMessage?.role === "assistant" && lastMessage.isStreaming) {
            return [
              ...prev.slice(0, -1),
              {
                ...lastMessage,
                content: lastMessage.content + data.content,
                isStreaming: !isLast,
              },
            ]
          }

          return [
            ...prev,
            {
              id: Date.now().toString(),
              role: "assistant",
              content: data.content,
              timestamp: new Date(),
              isStreaming: !isLast,
            },
          ]
        })
      } else if (data.type === "status") {
        if (data.metadata?.topic) {
          setCurrentTopic(data.metadata.topic)
        }
      } else if (data.type === "quiz") {
        console.log("❓ QUIZ RECEIVED:", data.question)
        setActiveQuiz(data.question)
        console.log("❓ activeQuiz state should now be set")
      } else if (data.type === "mastery_update") {
        if (data.mastery) {
          const topicList = Object.entries(data.mastery).map(([id, score]) => ({
            id: parseInt(id),
            title: `Topic ${id}`,
            mastery: score as number,
          }))
          setTopics(topicList)
        }
      } else if (data.type === "quiz_result") {
        // Show quiz result
        if (data.is_correct) {
          toast.success("Correct! 🎉")
        } else {
          toast.error(data.feedback || "Not quite right.")
        }
      }
    }

    wsRef.current.onclose = () => setIsConnected(false)
    wsRef.current.onerror = () => {
      setIsConnected(false)
      toast.error("WebSocket connection error. Falling back to HTTP when needed.")
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
    const messageContent = inputMessage
    setInputMessage("")

    // Set loading state in a separate update to ensure it takes effect
    setIsLoading(true)

    try {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({
          type: "message",
          message: messageContent,
          student_id: studentId,
          course_id: courseId,
        }))
        // Don't clear loading here - it will be cleared when we receive the last token
        return
      }

      const response = await tutorApi.chat(sessionId, messageContent)
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
      setIsLoading(false)
    } finally {
      // Only clear loading for HTTP fallback path
      if (wsRef.current?.readyState !== WebSocket.OPEN) {
        setIsLoading(false)
      }
    }
  }

  const handleQuizAnswer = async (answer: string) => {
    if (!sessionId || !activeQuiz) return

    // Send answer via WebSocket
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: "quiz_answer",
        question_id: activeQuiz.question_id,
        answer,
      }))
    }

    setActiveQuiz(null)
  }

  const handleLogout = () => {
    logout()
    router.push("/auth/login")
  }

  const getMasteryColor = (mastery: number) => {
    if (mastery >= 0.8) return "bg-green-500"
    if (mastery >= 0.5) return "bg-yellow-500"
    return "bg-red-500"
  }

  const getRelativeTime = (date: Date | string) => {
    const now = new Date()
    const messageDate = typeof date === 'string' ? new Date(date) : date
    const seconds = Math.floor((now.getTime() - messageDate.getTime()) / 1000)

    if (seconds < 60) return "just now"
    const minutes = Math.floor(seconds / 60)
    if (minutes < 60) return `${minutes}m ago`
    const hours = Math.floor(minutes / 60)
    if (hours < 24) return `${hours}h ago`
    const days = Math.floor(hours / 24)
    return `${days}d ago`
  }

  const handleCopyMessage = async (messageId: string, content: string) => {
    try {
      await navigator.clipboard.writeText(content)
      setCopiedMessageId(messageId)
      setTimeout(() => setCopiedMessageId(null), 2000)
      toast.success("Copied to clipboard")
    } catch (error) {
      toast.error("Failed to copy")
    }
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
        <div className="container mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button
              variant="ghost"
              size="icon"
              className="lg:hidden"
              onClick={() => setSidebarOpen(!sidebarOpen)}
            >
              {sidebarOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </Button>
            <Link href="/" className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary to-purple-600 flex items-center justify-center">
                <BookOpen className="w-5 h-5 text-white" />
              </div>
              <span className="font-semibold hidden sm:inline">{courseTitle || "Learning"}</span>
            </Link>
          </div>

          <div className="flex items-center gap-4">
            <Link href="/student/browse">
              <Button variant="ghost" size="sm">
                <Home className="w-4 h-4" />
                <span className="hidden sm:inline ml-2">Browse</span>
              </Button>
            </Link>
            <Button variant="ghost" size="sm" onClick={handleLogout}>
              <LogOut className="w-4 h-4" />
            </Button>
          </div>
        </div>
      </header>

      <div className="flex-1 container mx-auto px-4 py-6">
        <div className="grid lg:grid-cols-4 gap-6 h-[calc(100vh-120px)]">
          {/* Sidebar - Progress & Topics */}
          <div
            className={cn(
              "lg:col-span-1 space-y-4 transition-transform",
              sidebarOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0 fixed lg:relative inset-y-0 left-0 z-40 w-80 p-4 bg-background lg:bg-transparent border-r lg:border-0",
              !sidebarOpen && "hidden lg:block"
            )}
          >
            {/* Mastery Overview Card */}
            <Card className="glass">
              <div className="p-4 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="font-semibold flex items-center gap-2">
                    <Award className="w-4 h-4 text-primary" />
                    Your Progress
                  </h3>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="lg:hidden"
                    onClick={() => setSidebarOpen(false)}
                  >
                    <X className="w-4 h-4" />
                  </Button>
                </div>

                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Overall Mastery</span>
                    <span className="font-medium">{masteryScore.toFixed(0)}%</span>
                  </div>
                  <Progress value={masteryScore} className="h-2" />
                </div>

                <div className="flex items-center gap-2 text-sm">
                  <div className={cn(
                    "w-2 h-2 rounded-full",
                    isConnected ? "bg-green-500" : "bg-yellow-500"
                  )} />
                  <span className="text-muted-foreground">
                    {isConnected ? "Connected" : "Connecting..."}
                  </span>
                </div>
              </div>
            </Card>

            {/* Topics Progress */}
            <Card className="glass">
              <div className="p-4">
                <h3 className="font-semibold mb-4 flex items-center gap-2">
                  <Target className="w-4 h-4 text-primary" />
                  Topics
                </h3>
                <ScrollArea className="h-60">
                  <div className="space-y-3 pr-2">
                    {topics.map((topic) => (
                      <div key={topic.id} className="space-y-1">
                        <div className="flex justify-between text-sm">
                          <span className="truncate flex-1">{topic.title}</span>
                          <span className="text-muted-foreground">
                            {Math.round(topic.mastery * 100)}%
                          </span>
                        </div>
                        <Progress value={topic.mastery * 100} className="h-1" />
                      </div>
                    ))}
                    {topics.length === 0 && (
                      <p className="text-sm text-muted-foreground text-center py-4">
                        Start learning to track your progress
                      </p>
                    )}
                  </div>
                </ScrollArea>
              </div>
            </Card>

            {/* Quick Actions */}
            <Card className="glass">
              <div className="p-4 space-y-2">
                <h3 className="font-semibold mb-2">Quick Actions</h3>
                <Link href={`/student/progress/${courseId}`}>
                  <Button variant="outline" size="sm" className="w-full justify-start">
                    <TrendingUp className="w-4 h-4 mr-2" />
                    View Detailed Progress
                    <ChevronRight className="w-4 h-4 ml-auto" />
                  </Button>
                </Link>
              </div>
            </Card>
          </div>

          {/* Main Chat Area */}
          <div className="lg:col-span-3">
            <Card className="h-full flex flex-col glass">
              {/* Current Topic Indicator & Agent Status */}
              {(currentTopic || agentStatus !== "idle") && (
                <div className="px-4 py-2 border-b border-border/50 bg-gradient-to-r from-primary/5 to-purple-500/5">
                  <div className="flex items-center justify-between gap-2 text-sm">
                    {currentTopic ? (
                      <div className="flex items-center gap-2">
                        <Sparkles className="w-4 h-4 text-primary" />
                        <span className="text-primary font-medium">Learning: {currentTopic}</span>
                      </div>
                    ) : (
                      <div />
                    )}

                    {/* Agent Status Badge */}
                    {agentStatus !== "idle" && (
                      <Badge
                        variant="secondary"
                        className={cn(
                          "gap-1.5 transition-all",
                          agentStatus === "thinking" && "bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/20",
                          agentStatus === "typing" && "bg-primary/10 text-primary border-primary/20"
                        )}
                      >
                        {agentStatus === "thinking" ? (
                          <>
                            <Brain className="w-3 h-3 animate-pulse" />
                            <span>Thinking...</span>
                          </>
                        ) : (
                          <>
                            <Loader2 className="w-3 h-3 animate-spin" />
                            <span>Typing...</span>
                          </>
                        )}
                      </Badge>
                    )}
                  </div>
                </div>
              )}

              <CardContent className="flex-1 flex flex-col p-0">
                {/* Messages */}
                <ScrollArea className="flex-1 p-4">
                  <div className="space-y-6">
                    {console.log("📧 RENDERING MESSAGES - Count:", messages.length)}
                    {messages.map((message) => {
                      console.log("💬 Rendering message:", message.id, "Role:", message.role, "Has timestamp:", !!message.timestamp)
                      return (
                      <div
                        key={message.id}
                        className={cn(
                          "flex flex-col gap-1 animate-in slide-in-from-bottom-2 duration-300",
                          message.role === "user" ? "items-end" : "items-start"
                        )}
                      >
                        <div
                          className={cn(
                            "group relative max-w-[80%] rounded-2xl px-4 py-3 transition-all hover:scale-[1.01]",
                            message.role === "user"
                              ? "bg-gradient-to-r from-primary to-purple-600 text-white rounded-br-sm shadow-lg shadow-primary/25 hover:shadow-primary/40"
                              : "bg-muted text-foreground rounded-bl-sm hover:bg-muted/80"
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

                          {/* Copy button - VERY VISIBLE FOR TESTING */}
                          {message.role === "assistant" && !message.isStreaming && (
                            <button
                              className="absolute top-0 right-0 bg-red-500 text-white px-4 py-2 text-xs font-bold rounded"
                              onClick={() => {
                                console.log("COPY BUTTON CLICKED!")
                                handleCopyMessage(message.id, message.content)
                              }}
                            >
                              COPY ME!
                            </button>
                          )}
                        </div>

                        {/* Timestamp - VERY VISIBLE FOR TESTING */}
                        <div className={cn(
                          "text-sm font-bold bg-yellow-300 text-black px-3 py-1 rounded",
                          message.role === "user" ? "text-right" : "text-left"
                        )}>
                          TIMESTAMP: {message.timestamp ? String(new Date()) : "NO TIMESTAMP"}
                        </div>
                      </div>
                    )
                    })}
                    {isLoading && agentStatus === "thinking" && (
                      <div className="flex flex-col gap-1 items-start animate-in slide-in-from-bottom-2 duration-300">
                        <div className="max-w-[80%] rounded-2xl px-5 py-3.5 bg-gradient-to-r from-muted to-muted/80 rounded-bl-sm shadow-sm">
                          <div className="flex items-center gap-2">
                            <Brain className="w-4 h-4 text-amber-500 animate-pulse" />
                            <div className="flex gap-1.5">
                              <span className="typing-dot bg-amber-500/60" style={{ animationDelay: "0ms" }} />
                              <span className="typing-dot bg-amber-500/60" style={{ animationDelay: "150ms" }} />
                              <span className="typing-dot bg-amber-500/60" style={{ animationDelay: "300ms" }} />
                            </div>
                          </div>
                        </div>
                        <span className="text-xs text-muted-foreground px-2">just now</span>
                      </div>
                    )}
                  </div>
                  <div ref={messagesEndRef} />
                </ScrollArea>

                {/* Quiz Section - Collapsible */}
                {console.log("🎯 Checking activeQuiz:", activeQuiz, "Collapsed:", quizCollapsed)}
                {activeQuiz && (
                  <div className="border-t border-border/50 bg-gradient-to-b from-primary/5 to-muted/30" style={{ border: "5px solid red" }}>
                    {/* Header - Always Visible */}
                    <div
                      className="px-4 py-3 flex items-center justify-between cursor-pointer hover:bg-muted/20 transition-colors"
                      onClick={() => setQuizCollapsed(!quizCollapsed)}
                    >
                      <div className="flex items-center gap-2 text-sm font-medium">
                        <MessageSquare className="w-4 h-4 text-primary" />
                        <span className="text-primary">Quiz Time!</span>
                        {quizCollapsed && (
                          <Badge variant="secondary" className="ml-2 text-xs">
                            Click to expand
                          </Badge>
                        )}
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 shrink-0"
                        onClick={(e) => {
                          e.stopPropagation()
                          setQuizCollapsed(!quizCollapsed)
                        }}
                      >
                        {quizCollapsed ? (
                          <ChevronDown className="w-4 h-4" />
                        ) : (
                          <ChevronUp className="w-4 h-4" />
                        )}
                      </Button>
                    </div>

                    {/* Question Content - Collapsible */}
                    {!quizCollapsed && (
                      <div className="px-4 pb-4 space-y-3 animate-in slide-in-from-top-2 duration-200">
                        <p className="text-sm font-medium">{activeQuiz.question_text}</p>

                        {activeQuiz.question_type === "multiple_choice" && activeQuiz.options && (
                          <div className="space-y-2">
                            {activeQuiz.options.map((option, index) => (
                              <Button
                                key={index}
                                variant="outline"
                                className="w-full justify-start h-auto py-3 px-4 hover:bg-primary/10 hover:border-primary transition-colors"
                                onClick={() => handleQuizAnswer(option.value)}
                              >
                                {option.text}
                              </Button>
                            ))}
                          </div>
                        )}

                        {activeQuiz.question_type === "true_false" && (
                          <div className="flex gap-3">
                            <Button
                              className="flex-1"
                              onClick={() => handleQuizAnswer("true")}
                            >
                              True
                            </Button>
                            <Button
                              variant="outline"
                              className="flex-1"
                              onClick={() => handleQuizAnswer("false")}
                            >
                              False
                            </Button>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {/* Input */}
                <div className="p-4 border-t border-border/50">
                  <div className="flex gap-2">
                    <Textarea
                      ref={textareaRef}
                      placeholder="Ask a question or share what you're learning..."
                      value={inputMessage}
                      onChange={(e) => setInputMessage(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), handleSendMessage())}
                      className="flex-1 min-h-[44px] max-h-40 overflow-y-auto"
                      disabled={!!activeQuiz}
                    />
                    <Button
                      onClick={handleSendMessage}
                      disabled={!inputMessage.trim() || isLoading || !!activeQuiz}
                      size="icon"
                      className="button-press shrink-0"
                    >
                      {isLoading ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Send className="w-4 h-4" />
                      )}
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
