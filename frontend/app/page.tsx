import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ArrowRight, BookOpen, Users, Zap, Sparkles } from "lucide-react"

export default function HomePage() {
  return (
    <div className="min-h-screen gradient-bg bg-pattern">
      {/* Hero Section */}
      <section className="relative overflow-hidden">
        {/* Animated background elements */}
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          <div className="absolute -top-40 -right-40 w-80 h-80 bg-primary/20 rounded-full blur-3xl animate-pulse-glow" />
          <div className="absolute -bottom-40 -left-40 w-80 h-80 bg-purple-500/20 rounded-full blur-3xl animate-pulse-glow" style={{ animationDelay: '1s' }} />
        </div>

        <div className="container mx-auto px-4 py-20 md:py-32 relative">
          <div className="max-w-4xl mx-auto text-center space-y-8">
            {/* Badge */}
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-primary/10 border border-primary/20 glass interactive cursor-default">
              <Sparkles className="w-4 h-4 text-primary" />
              <span className="text-sm font-medium">AI-Powered Learning Platform</span>
            </div>

            {/* Main heading */}
            <h1 className="text-5xl md:text-7xl font-bold tracking-tight">
              <span className="block mb-2">Learn & Create with</span>
              <span className="gradient-text">Agentic AI Tutors</span>
            </h1>

            {/* Description */}
            <p className="text-xl text-muted-foreground max-w-2xl mx-auto leading-relaxed">
              Transform your knowledge into interactive courses with AI assistance,
              or learn with a personalized tutor that adapts to your unique learning style.
            </p>

            {/* CTA Buttons */}
            <div className="flex flex-col sm:flex-row gap-4 justify-center items-center pt-4">
              <Button asChild size="lg" className="button-press text-base px-8 h-12 shadow-lg shadow-primary/25">
                <Link href="/student/browse" className="flex items-center gap-2">
                  <BookOpen className="w-5 h-5" />
                  Start Learning
                  <ArrowRight className="w-4 h-4" />
                </Link>
              </Button>
              <Button asChild variant="outline" size="lg" className="button-press text-base px-8 h-12 glass">
                <Link href="/constructor/dashboard" className="flex items-center gap-2">
                  <Zap className="w-5 h-5" />
                  Create Course
                </Link>
              </Button>
            </div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-20 bg-muted/30">
        <div className="container mx-auto px-4">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-bold mb-4">
              Built for <span className="gradient-text">Everyone</span>
            </h2>
            <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
              Whether you're creating content or learning new skills, our AI agents make the experience seamless and engaging.
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6 max-w-6xl mx-auto">
            {/* Feature 1 */}
            <Card className="card-hover border-none shadow-lg bg-gradient-to-br from-card to-card/50">
              <CardHeader>
                <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center mb-4">
                  <Zap className="w-6 h-6 text-primary" />
                </div>
                <CardTitle>AI Course Creation</CardTitle>
                <CardDescription>
                  Upload your materials and let AI agents structure, organize, and generate assessments automatically.
                </CardDescription>
              </CardHeader>
            </Card>

            {/* Feature 2 */}
            <Card className="card-hover border-none shadow-lg bg-gradient-to-br from-card to-card/50">
              <CardHeader>
                <div className="w-12 h-12 rounded-xl bg-purple-500/10 flex items-center justify-center mb-4">
                  <Users className="w-6 h-6 text-purple-500" />
                </div>
                <CardTitle>Personalized Learning</CardTitle>
                <CardDescription>
                  AI tutors adapt to your learning style, track your progress, and focus on areas where you need improvement.
                </CardDescription>
              </CardHeader>
            </Card>

            {/* Feature 3 */}
            <Card className="card-hover border-none shadow-lg bg-gradient-to-br from-card to-card/50">
              <CardHeader>
                <div className="w-12 h-12 rounded-xl bg-pink-500/10 flex items-center justify-center mb-4">
                  <Sparkles className="w-6 h-6 text-pink-500" />
                </div>
                <CardTitle>Real-time Interaction</CardTitle>
                <CardDescription>
                  Engage in natural conversations with AI agents that provide instant feedback and explanations.
                </CardDescription>
              </CardHeader>
            </Card>
          </div>
        </div>
      </section>

      {/* Stats Section */}
      <section className="py-20">
        <div className="container mx-auto px-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8 max-w-4xl mx-auto text-center">
            <div className="space-y-2">
              <div className="text-4xl font-bold gradient-text">AI+</div>
              <div className="text-sm text-muted-foreground">Agents Working</div>
            </div>
            <div className="space-y-2">
              <div className="text-4xl font-bold gradient-text">∞</div>
              <div className="text-sm text-muted-foreground">Learning Paths</div>
            </div>
            <div className="space-y-2">
              <div className="text-4xl font-bold gradient-text">24/7</div>
              <div className="text-sm text-muted-foreground">Availability</div>
            </div>
            <div className="space-y-2">
              <div className="text-4xl font-bold gradient-text">100%</div>
              <div className="text-sm text-muted-foreground">Personalized</div>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20 bg-muted/30">
        <div className="container mx-auto px-4">
          <Card className="max-w-2xl mx-auto border-primary/20 bg-gradient-to-br from-primary/5 to-purple-500/5">
            <CardHeader className="text-center pb-4">
              <CardTitle className="text-2xl md:text-3xl">Ready to Get Started?</CardTitle>
              <CardDescription className="text-base">
                Join thousands of learners and creators transforming education with AI.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col sm:flex-row gap-4 justify-center">
              <Button asChild size="lg" className="button-press">
                <Link href="/auth/login">Sign In</Link>
              </Button>
              <Button asChild variant="outline" size="lg" className="button-press">
                <Link href="/auth/register">Create Account</Link>
              </Button>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-8 border-t border-border/50">
        <div className="container mx-auto px-4 text-center text-sm text-muted-foreground">
          <p>© 2024 Agentic Tutor. Building the future of education with AI.</p>
        </div>
      </footer>
    </div>
  )
}
