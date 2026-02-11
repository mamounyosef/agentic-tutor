"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import * as z from "zod"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { BookOpen, Zap, Loader2 } from "lucide-react"
import { useAuthStore } from "@/lib/store"
import { authApi } from "@/lib/api"
import { cn } from "@/lib/utils"

const creatorLoginSchema = z.object({
  email: z.string().email("Invalid email address"),
  password: z.string().min(6, "Password must be at least 6 characters"),
})

const studentLoginSchema = z.object({
  email: z.string().email("Invalid email address"),
  password: z.string().min(6, "Password must be at least 6 characters"),
})

type CreatorLoginForm = z.infer<typeof creatorLoginSchema>
type StudentLoginForm = z.infer<typeof studentLoginSchema>

export default function LoginPage() {
  const router = useRouter()
  const { setCreatorAuth, setStudentAuth } = useAuthStore()
  const [isLoading, setIsLoading] = useState(false)
  const [activeTab, setActiveTab] = useState<"creator" | "student">("creator")

  const creatorForm = useForm<CreatorLoginForm>({
    resolver: zodResolver(creatorLoginSchema),
    defaultValues: { email: "", password: "" },
  })

  const studentForm = useForm<StudentLoginForm>({
    resolver: zodResolver(studentLoginSchema),
    defaultValues: { email: "", password: "" },
  })

  const onCreatorLogin = async (data: CreatorLoginForm) => {
    setIsLoading(true)
    try {
      const response = await authApi.loginCreator(data.email, data.password)
      setCreatorAuth(
        response.access_token,
        response.user_id,
        "", // Name will be fetched from /me
        data.email
      )
      toast.success("Welcome back, Creator!")
      router.push("/constructor/dashboard")
    } catch (error: any) {
      toast.error(error.response?.data?.detail || "Login failed. Please check your credentials.")
    } finally {
      setIsLoading(false)
    }
  }

  const onStudentLogin = async (data: StudentLoginForm) => {
    setIsLoading(true)
    try {
      const response = await authApi.loginStudent(data.email, data.password)
      setStudentAuth(
        response.access_token,
        response.user_id,
        "", // Name will be fetched from /me
        data.email
      )
      toast.success("Welcome back, Student!")
      router.push("/student/browse")
    } catch (error: any) {
      toast.error(error.response?.data?.detail || "Login failed. Please check your credentials.")
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center gradient-bg bg-pattern p-4">
      {/* Animated background elements */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 -left-20 w-72 h-72 bg-primary/10 rounded-full blur-3xl animate-pulse" />
        <div className="absolute bottom-1/4 -right-20 w-72 h-72 bg-purple-500/10 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '1s' }} />
      </div>

      <div className="w-full max-w-md relative z-10">
        {/* Logo/Brand */}
        <div className="text-center mb-8 animate-fade-in">
          <Link href="/" className="inline-flex items-center gap-2">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary to-purple-600 flex items-center justify-center shadow-lg shadow-primary/25">
              <BookOpen className="w-6 h-6 text-white" />
            </div>
            <span className="text-2xl font-bold">Agentic Tutor</span>
          </Link>
        </div>

        <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as "creator" | "student")} className="w-full">
          <Card className="border-none shadow-2xl bg-card/80 backdrop-blur-xl">
            <CardHeader className="text-center space-y-2 pb-6">
              <CardTitle className="text-2xl">Welcome back</CardTitle>
              <CardDescription>
                Sign in to continue to your learning journey
              </CardDescription>
            </CardHeader>
            <CardContent>
              <TabsList className="grid w-full grid-cols-2 mb-6">
                <TabsTrigger value="creator" className="data-[state=active]:bg-primary data-[state=active]:text-primary-foreground">
                  <Zap className="w-4 h-4 mr-2" />
                  Creator
                </TabsTrigger>
                <TabsTrigger value="student" className="data-[state=active]:bg-primary data-[state=active]:text-primary-foreground">
                  <BookOpen className="w-4 h-4 mr-2" />
                  Student
                </TabsTrigger>
              </TabsList>

              {/* Creator Login Form */}
              <TabsContent value="creator" className="space-y-4 animate-fade-in">
                <form onSubmit={creatorForm.handleSubmit(onCreatorLogin)} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="creator-email">Email</Label>
                    <Input
                      id="creator-email"
                      type="email"
                      placeholder="creator@example.com"
                      {...creatorForm.register("email")}
                      className={cn(
                        "transition-all duration-200",
                        creatorForm.formState.errors.email && "border-destructive focus:border-destructive"
                      )}
                    />
                    {creatorForm.formState.errors.email && (
                      <p className="text-sm text-destructive">{creatorForm.formState.errors.email.message}</p>
                    )}
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="creator-password">Password</Label>
                    <Input
                      id="creator-password"
                      type="password"
                      placeholder="••••••••"
                      {...creatorForm.register("password")}
                      className={cn(
                        "transition-all duration-200",
                        creatorForm.formState.errors.password && "border-destructive focus:border-destructive"
                      )}
                    />
                    {creatorForm.formState.errors.password && (
                      <p className="text-sm text-destructive">{creatorForm.formState.errors.password.message}</p>
                    )}
                  </div>

                  <Button
                    type="submit"
                    className="w-full button-press"
                    disabled={isLoading}
                  >
                    {isLoading ? (
                      <>
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        Signing in...
                      </>
                    ) : (
                      "Sign In as Creator"
                    )}
                  </Button>
                </form>
              </TabsContent>

              {/* Student Login Form */}
              <TabsContent value="student" className="space-y-4 animate-fade-in">
                <form onSubmit={studentForm.handleSubmit(onStudentLogin)} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="student-email">Email</Label>
                    <Input
                      id="student-email"
                      type="email"
                      placeholder="student@example.com"
                      {...studentForm.register("email")}
                      className={cn(
                        "transition-all duration-200",
                        studentForm.formState.errors.email && "border-destructive focus:border-destructive"
                      )}
                    />
                    {studentForm.formState.errors.email && (
                      <p className="text-sm text-destructive">{studentForm.formState.errors.email.message}</p>
                    )}
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="student-password">Password</Label>
                    <Input
                      id="student-password"
                      type="password"
                      placeholder="••••••••"
                      {...studentForm.register("password")}
                      className={cn(
                        "transition-all duration-200",
                        studentForm.formState.errors.password && "border-destructive focus:border-destructive"
                      )}
                    />
                    {studentForm.formState.errors.password && (
                      <p className="text-sm text-destructive">{studentForm.formState.errors.password.message}</p>
                    )}
                  </div>

                  <Button
                    type="submit"
                    className="w-full button-press"
                    disabled={isLoading}
                  >
                    {isLoading ? (
                      <>
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        Signing in...
                      </>
                    ) : (
                      "Sign In as Student"
                    )}
                  </Button>
                </form>
              </TabsContent>

              {/* Footer */}
              <div className="mt-6 text-center text-sm text-muted-foreground">
                Don't have an account?{" "}
                <Link href="/auth/register" className="text-primary hover:underline font-medium">
                  Sign up
                </Link>
              </div>
            </CardContent>
          </Card>
        </Tabs>
      </div>
    </div>
  )
}
