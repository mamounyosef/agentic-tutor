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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { BookOpen, Zap, Loader2, ArrowLeft } from "lucide-react"
import { useAuthStore } from "@/lib/store"
import { authApi } from "@/lib/api"
import { cn } from "@/lib/utils"

const creatorSchema = z.object({
  email: z.string().email("Invalid email address"),
  password: z.string().min(6, "Password must be at least 6 characters"),
  fullName: z.string().min(2, "Name must be at least 2 characters"),
})

const studentSchema = z.object({
  email: z.string().email("Invalid email address"),
  password: z.string().min(6, "Password must be at least 6 characters"),
  fullName: z.string().min(2, "Name must be at least 2 characters"),
  age: z.string().optional(),
  gender: z.string().optional(),
  educationLevel: z.string().optional(),
})

type CreatorForm = z.infer<typeof creatorSchema>
type StudentForm = z.infer<typeof studentSchema>

export default function RegisterPage() {
  const router = useRouter()
  const { setCreatorAuth, setStudentAuth } = useAuthStore()
  const [isLoading, setIsLoading] = useState(false)
  const [activeTab, setActiveTab] = useState<"creator" | "student">("creator")

  const creatorForm = useForm<CreatorForm>({
    resolver: zodResolver(creatorSchema),
    defaultValues: { email: "", password: "", fullName: "" },
  })

  const studentForm = useForm<StudentForm>({
    resolver: zodResolver(studentSchema),
    defaultValues: {
      email: "",
      password: "",
      fullName: "",
      age: "",
      gender: "",
      educationLevel: ""
    },
  })

  const onCreatorRegister = async (data: CreatorForm) => {
    setIsLoading(true)
    try {
      const response = await authApi.registerCreator(data.email, data.password, data.fullName)
      setCreatorAuth(
        response.access_token,
        response.user_id,
        data.fullName,
        data.email
      )
      toast.success("Account created successfully!")
      router.push("/constructor/dashboard")
    } catch (error: any) {
      toast.error(error.response?.data?.detail || "Registration failed. Please try again.")
    } finally {
      setIsLoading(false)
    }
  }

  const onStudentRegister = async (data: StudentForm) => {
    setIsLoading(true)
    try {
      const response = await authApi.registerStudent(
        data.email,
        data.password,
        data.fullName,
        data.age ? parseInt(data.age) : undefined,
        data.gender || undefined,
        data.educationLevel || undefined
      )
      setStudentAuth(
        response.access_token,
        response.user_id,
        data.fullName,
        data.email
      )
      toast.success("Account created successfully!")
      router.push("/student/browse")
    } catch (error: any) {
      toast.error(error.response?.data?.detail || "Registration failed. Please try again.")
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center gradient-bg bg-pattern p-4">
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 -left-20 w-72 h-72 bg-primary/10 rounded-full blur-3xl animate-pulse" />
        <div className="absolute bottom-1/4 -right-20 w-72 h-72 bg-purple-500/10 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '1s' }} />
      </div>

      <div className="w-full max-w-md relative z-10">
        {/* Back button */}
        <Link href="/" className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground mb-6 interactive">
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back to home
        </Link>

        <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as "creator" | "student")} className="w-full">
          <Card className="border-none shadow-2xl bg-card/80 backdrop-blur-xl">
            <CardHeader className="text-center space-y-2 pb-6">
              <CardTitle className="text-2xl">Create an account</CardTitle>
              <CardDescription>
                Join the future of AI-powered learning
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

              {/* Creator Register Form */}
              <TabsContent value="creator" className="space-y-4 animate-fade-in">
                <form onSubmit={creatorForm.handleSubmit(onCreatorRegister)} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="creator-name">Full Name</Label>
                    <Input
                      id="creator-name"
                      type="text"
                      placeholder="John Doe"
                      {...creatorForm.register("fullName")}
                      className={cn(creatorForm.formState.errors.fullName && "border-destructive")}
                    />
                    {creatorForm.formState.errors.fullName && (
                      <p className="text-sm text-destructive">{creatorForm.formState.errors.fullName.message}</p>
                    )}
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="creator-email">Email</Label>
                    <Input
                      id="creator-email"
                      type="email"
                      placeholder="creator@example.com"
                      {...creatorForm.register("email")}
                      className={cn(creatorForm.formState.errors.email && "border-destructive")}
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
                      className={cn(creatorForm.formState.errors.password && "border-destructive")}
                    />
                    {creatorForm.formState.errors.password && (
                      <p className="text-sm text-destructive">{creatorForm.formState.errors.password.message}</p>
                    )}
                  </div>

                  <Button type="submit" className="w-full button-press" disabled={isLoading}>
                    {isLoading ? (
                      <>
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        Creating account...
                      </>
                    ) : (
                      "Create Creator Account"
                    )}
                  </Button>
                </form>
              </TabsContent>

              {/* Student Register Form */}
              <TabsContent value="student" className="space-y-4 animate-fade-in">
                <form onSubmit={studentForm.handleSubmit(onStudentRegister)} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="student-name">Full Name</Label>
                    <Input
                      id="student-name"
                      type="text"
                      placeholder="John Doe"
                      {...studentForm.register("fullName")}
                      className={cn(studentForm.formState.errors.fullName && "border-destructive")}
                    />
                    {studentForm.formState.errors.fullName && (
                      <p className="text-sm text-destructive">{studentForm.formState.errors.fullName.message}</p>
                    )}
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="student-email">Email</Label>
                    <Input
                      id="student-email"
                      type="email"
                      placeholder="student@example.com"
                      {...studentForm.register("email")}
                      className={cn(studentForm.formState.errors.email && "border-destructive")}
                    />
                    {studentForm.formState.errors.email && (
                      <p className="text-sm text-destructive">{studentForm.formState.errors.email.message}</p>
                    )}
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="student-age">Age (Optional)</Label>
                      <Input
                        id="student-age"
                        type="number"
                        placeholder="25"
                        {...studentForm.register("age")}
                      />
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="student-gender">Gender (Optional)</Label>
                      <Select onValueChange={(val) => studentForm.setValue("gender", val)}>
                        <SelectTrigger>
                          <SelectValue placeholder="Select" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="male">Male</SelectItem>
                          <SelectItem value="female">Female</SelectItem>
                          <SelectItem value="other">Other</SelectItem>
                          <SelectItem value="prefer_not_to_say">Prefer not to say</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="student-education">Education Level (Optional)</Label>
                    <Select onValueChange={(val) => studentForm.setValue("educationLevel", val)}>
                      <SelectTrigger>
                        <SelectValue placeholder="Select your education" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="high_school">High School</SelectItem>
                        <SelectItem value="undergraduate">Undergraduate</SelectItem>
                        <SelectItem value="graduate">Graduate</SelectItem>
                        <SelectItem value="postgraduate">Postgraduate</SelectItem>
                        <SelectItem value="other">Other</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="student-password">Password</Label>
                    <Input
                      id="student-password"
                      type="password"
                      placeholder="••••••••"
                      {...studentForm.register("password")}
                      className={cn(studentForm.formState.errors.password && "border-destructive")}
                    />
                    {studentForm.formState.errors.password && (
                      <p className="text-sm text-destructive">{studentForm.formState.errors.password.message}</p>
                    )}
                  </div>

                  <Button type="submit" className="w-full button-press" disabled={isLoading}>
                    {isLoading ? (
                      <>
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        Creating account...
                      </>
                    ) : (
                      "Create Student Account"
                    )}
                  </Button>
                </form>
              </TabsContent>

              {/* Footer */}
              <div className="mt-6 text-center text-sm text-muted-foreground">
                Already have an account?{" "}
                <Link href="/auth/login" className="text-primary hover:underline font-medium">
                  Sign in
                </Link>
              </div>
            </CardContent>
          </Card>
        </Tabs>
      </div>
    </div>
  )
}
