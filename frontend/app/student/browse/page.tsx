"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  BookOpen,
  Search,
  Zap,
  Loader2,
  LogOut,
  TrendingUp,
  Clock,
  Users,
  ArrowRight,
  Filter,
} from "lucide-react"
import { useAuthStore } from "@/lib/store"
import { tutorApi } from "@/lib/api"
import { cn } from "@/lib/utils"

interface Course {
  id: number
  title: string
  description: string
  difficulty: "beginner" | "intermediate" | "advanced"
  created_at: string
  units?: number
  topics?: number
}

export default function StudentBrowse() {
  const router = useRouter()
  const { studentToken, studentId, logout } = useAuthStore()
  const [courses, setCourses] = useState<Course[]>([])
  const [filteredCourses, setFilteredCourses] = useState<Course[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState("")
  const [selectedDifficulty, setSelectedDifficulty] = useState<string>("all")

  useEffect(() => {
    if (!studentToken) {
      router.push("/auth/login")
      return
    }
    loadCourses()
  }, [])

  useEffect(() => {
    // Filter courses
    let filtered = courses

    if (searchQuery) {
      filtered = filtered.filter(
        (course) =>
          course.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
          course.description.toLowerCase().includes(searchQuery.toLowerCase())
      )
    }

    if (selectedDifficulty !== "all") {
      filtered = filtered.filter((course) => course.difficulty === selectedDifficulty)
    }

    setFilteredCourses(filtered)
  }, [courses, searchQuery, selectedDifficulty])

  const loadCourses = async () => {
    try {
      const data = await tutorApi.listCourses()
      setCourses(data)
      setFilteredCourses(data)
    } catch (error) {
      toast.error("Failed to load courses")
    } finally {
      setIsLoading(false)
    }
  }

  const handleEnroll = async (courseId: number) => {
    try {
      await tutorApi.enrollInCourse(courseId)
      toast.success("Successfully enrolled in course!")
      router.push(`/student/learn/${courseId}`)
    } catch (error: any) {
      toast.error(error.response?.data?.detail || "Failed to enroll")
    }
  }

  const getDifficultyColor = (difficulty: string) => {
    switch (difficulty) {
      case "beginner":
        return "bg-green-500/10 text-green-500 border-green-500/20"
      case "intermediate":
        return "bg-yellow-500/10 text-yellow-500 border-yellow-500/20"
      case "advanced":
        return "bg-red-500/10 text-red-500 border-red-500/20"
      default:
        return "bg-muted"
    }
  }

  const handleLogout = () => {
    logout()
    router.push("/auth/login")
  }

  return (
    <div className="min-h-screen flex flex-col gradient-bg">
      {/* Header */}
      <header className="border-b border-border/50 bg-card/50 backdrop-blur-xl sticky top-0 z-50">
        <div className="container mx-auto px-4 h-16 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary to-purple-600 flex items-center justify-center">
              <BookOpen className="w-5 h-5 text-white" />
            </div>
            <span className="font-semibold">Learning Hub</span>
          </Link>

          <div className="flex items-center gap-4">
            <Link href="/student/progress">
              <Button variant="ghost" size="sm">My Progress</Button>
            </Link>
            <Button variant="ghost" size="sm" onClick={handleLogout}>
              <LogOut className="w-4 h-4" />
            </Button>
          </div>
        </div>
      </header>

      <div className="flex-1 container mx-auto px-4 py-8">
        {/* Hero Section */}
        <div className="text-center mb-12 animate-fade-in">
          <h1 className="text-4xl md:text-5xl font-bold mb-4">
            Explore <span className="gradient-text">Courses</span>
          </h1>
          <p className="text-xl text-muted-foreground max-w-2xl mx-auto">
            Discover AI-powered courses and start your personalized learning journey today.
          </p>
        </div>

        {/* Search and Filters */}
        <div className="max-w-4xl mx-auto mb-8 space-y-4">
          <div className="relative">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-muted-foreground" />
            <Input
              placeholder="Search courses..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-12 h-12 text-base glass"
            />
          </div>

          <div className="flex items-center gap-3">
            <Filter className="w-4 h-4 text-muted-foreground" />
            <div className="flex gap-2">
              <Button
                variant={selectedDifficulty === "all" ? "default" : "outline"}
                size="sm"
                onClick={() => setSelectedDifficulty("all")}
              >
                All Levels
              </Button>
              <Button
                variant={selectedDifficulty === "beginner" ? "default" : "outline"}
                size="sm"
                onClick={() => setSelectedDifficulty("beginner")}
              >
                Beginner
              </Button>
              <Button
                variant={selectedDifficulty === "intermediate" ? "default" : "outline"}
                size="sm"
                onClick={() => setSelectedDifficulty("intermediate")}
              >
                Intermediate
              </Button>
              <Button
                variant={selectedDifficulty === "advanced" ? "default" : "outline"}
                size="sm"
                onClick={() => setSelectedDifficulty("advanced")}
              >
                Advanced
              </Button>
            </div>
          </div>
        </div>

        {/* Course Grid */}
        {isLoading ? (
          <div className="flex justify-center py-20">
            <Loader2 className="w-8 h-8 animate-spin text-primary" />
          </div>
        ) : filteredCourses.length === 0 ? (
          <div className="text-center py-20">
            <p className="text-muted-foreground text-lg">No courses found matching your search.</p>
          </div>
        ) : (
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6 max-w-6xl mx-auto">
            {filteredCourses.map((course, index) => (
              <Card
                key={course.id}
                className="card-hover border-none shadow-lg bg-gradient-to-br from-card to-card/50 overflow-hidden group"
                style={{ animationDelay: `${index * 50}ms` }}
              >
                <CardHeader>
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <Badge variant="outline" className={getDifficultyColor(course.difficulty)}>
                      {course.difficulty}
                    </Badge>
                  </div>
                  <CardTitle className="line-clamp-2">{course.title}</CardTitle>
                  <CardDescription className="line-clamp-3">
                    {course.description}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center justify-between text-sm text-muted-foreground mb-4">
                    <div className="flex items-center gap-1">
                      <BookOpen className="w-4 h-4" />
                      <span>{course.units || 0} units</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <Clock className="w-4 h-4" />
                      <span>Self-paced</span>
                    </div>
                  </div>

                  <Button
                    className="w-full button-press"
                    onClick={() => handleEnroll(course.id)}
                  >
                    <Users className="w-4 h-4 mr-2" />
                    Start Learning
                    <ArrowRight className="w-4 h-4 ml-2" />
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
