"use client"

import { useState, useEffect, useRef } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
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
} from "lucide-react"
import { useAuthStore } from "@/lib/store"
import { tutorApi } from "@/lib/api"
import { cn } from "@/lib/utils"

interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  timestamp: Date
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
  const router = useRouter()
  const { studentToken, studentId, logout } = useAuthStore()
  const courseId = parseInt(params.courseId)

  const [messages, setMessages] = useState<Message[]>([])
  const [inputMessage, setInputMessage] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [isConnected, setIsConnected] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [courseTitle, setCourseTitle] = useState("")
  const [topics, setTopics] = useState<Topic[]>([])
  const [currentTopic, setCurrentTopic] = useState<string>("")
  const [masteryScore, setMasteryScore] = useState(0)
  const [activeQuiz, setActiveQuiz] = useState<QuizQuestion | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    if (!studentToken) {
      router.push("/auth/login")
      return
    }
    initializeSession()
    loadCourseDetails()

    return () => {
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const initializeSession = async () => {
    try {
      const response = await tutorApi.startSession(courseId)
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

  const connectWebSocket = (sessionId: string) => {
    const apiBase = process.env.NEXT_PUBLIC_API_URL || `${window.location.protocol}//${window.location.host}`
    const wsBase = apiBase.replace(/^http/, "ws")
    const wsUrl = `${wsBase}/api/v1/tutor/session/ws/${sessionId}`

    wsRef.current = new WebSocket(wsUrl)

    wsRef.current.onopen = () => {
      setIsConnected(true)
    }

    wsRef.current.onmessage = (event) => {
      const data = JSON.parse(event.data)

      if (data.type === "token") {
        // Streaming token
        setMessages((prev) => {
          const lastMessage = prev[prev.length - 1]
          if (lastMessage?.role === "assistant" && lastMessage.isStreaming) {
            return [
              ...prev.slice(0, -1),
              {
                ...lastMessage,
                content: lastMessage.content + data.content,
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
              isStreaming: true,
            },
          ]
        })
      } else if (data.type === "status") {
        if (data.metadata?.topic) {
          setCurrentTopic(data.metadata.topic)
        }
      } else if (data.type === "quiz") {
        setActiveQuiz(data.question)
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
    setInputMessage("")
    setIsLoading(true)

    try {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({
          type: "message",
          message: userMessage.content,
          student_id: studentId,
          course_id: courseId,
        }))
        return
      }

      const response = await tutorApi.chat(sessionId, userMessage.content)
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
              {/* Current Topic Indicator */}
              {currentTopic && (
                <div className="px-4 py-2 border-b border-border/50 bg-primary/5">
                  <div className="flex items-center gap-2 text-sm">
                    <Sparkles className="w-4 h-4 text-primary" />
                    <span className="text-primary font-medium">Learning: {currentTopic}</span>
                  </div>
                </div>
              )}

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
                              ? "bg-gradient-to-r from-primary to-purple-600 text-white rounded-br-sm shadow-lg shadow-primary/25"
                              : "bg-muted text-foreground rounded-bl-sm"
                          )}
                        >
                          <p className="whitespace-pre-wrap">{message.content}</p>
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

                {/* Quiz Section */}
                {activeQuiz && (
                  <div className="p-4 border-t border-border/50 bg-muted/30">
                    <div className="space-y-3">
                      <div className="flex items-center gap-2 text-sm font-medium">
                        <MessageSquare className="w-4 h-4 text-primary" />
                        Quiz Time!
                      </div>
                      <p className="text-sm">{activeQuiz.question_text}</p>

                      {activeQuiz.question_type === "multiple_choice" && activeQuiz.options && (
                        <div className="space-y-2">
                          {activeQuiz.options.map((option, index) => (
                            <Button
                              key={index}
                              variant="outline"
                              className="w-full justify-start h-auto py-3 px-4"
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
                  </div>
                )}

                {/* Input */}
                <div className="p-4 border-t border-border/50">
                  <div className="flex gap-2">
                    <Input
                      placeholder="Ask a question or share what you're learning..."
                      value={inputMessage}
                      onChange={(e) => setInputMessage(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), handleSendMessage())}
                      className="flex-1"
                      disabled={!!activeQuiz}
                    />
                    <Button
                      onClick={handleSendMessage}
                      disabled={!inputMessage.trim() || isLoading || !!activeQuiz}
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
