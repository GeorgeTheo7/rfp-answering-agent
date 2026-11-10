import { useState, useEffect } from "react";
import { API_BASE } from "@/lib/api";
import { createFileRoute } from "@tanstack/react-router";
import { Target, BookOpen, Loader2, Activity } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AppHeader } from "@/components/AppHeader";
import { RfpSolver } from "@/components/RfpSolver";
import { KnowledgeBase } from "@/components/KnowledgeBase";
import { AccuracyEvaluator } from "@/components/AccuracyEvaluator";

export const Route = createFileRoute("/")({
  component: Index,
});

function Index() {
  const [isServerReady, setIsServerReady] = useState(false);
  const [isKbSyncing, setIsKbSyncing] = useState(false);
  const [isSolverProcessing, setIsSolverProcessing] = useState(false);
  const [isEvaluatorProcessing, setIsEvaluatorProcessing] = useState(false);

  const checkServerStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/providers/status`);
      if (res.ok) {
        setIsServerReady(true);
      } else {
        setTimeout(checkServerStatus, 3000);
      }
    } catch (error) {
      setTimeout(checkServerStatus, 3000);
    }
  };

  useEffect(() => {
    checkServerStatus();
  }, []);

  return (
    <div className="min-h-screen bg-background">
      <AppHeader />

      <main className="mx-auto max-w-7xl px-6 py-10">
        <div className="mb-8">
          <h1 className="text-3xl font-semibold tracking-tight text-foreground">
            RFP Solver & Evaluator
          </h1>
          <p className="mt-1.5 text-sm text-muted-foreground">
            Turn RFPs into completed responses with AI analysts grounded in your knowledge base.
          </p>
        </div>

        <Tabs defaultValue="kb" className="w-full">
          <TabsList className="h-11 bg-muted p-1">
            <TabsTrigger
              value="solver"
              disabled={!isServerReady || isKbSyncing || isEvaluatorProcessing}
              className="gap-2 px-4 text-sm data-[state=active]:shadow-soft disabled:opacity-50 disabled:cursor-not-allowed transition-all"
            >
              {isServerReady && !isKbSyncing && !isEvaluatorProcessing ? (
                <Target className="h-4 w-4" />
              ) : (
                <Loader2 className="h-4 w-4 animate-spin text-primary" />
              )}
              RFP Solver
            </TabsTrigger>

            <TabsTrigger
              value="kb"
              disabled={isSolverProcessing || isEvaluatorProcessing}
              className="gap-2 px-4 text-sm data-[state=active]:shadow-soft disabled:opacity-50 disabled:cursor-not-allowed transition-all"
            >
              {isSolverProcessing || isEvaluatorProcessing ? (
                <Loader2 className="h-4 w-4 animate-spin text-primary" />
              ) : (
                <BookOpen className="h-4 w-4" />
              )}
              Knowledge Base
            </TabsTrigger>

            <TabsTrigger
              value="evaluator"
              disabled={!isServerReady || isKbSyncing || isSolverProcessing}
              className="gap-2 px-4 text-sm data-[state=active]:shadow-soft disabled:opacity-50 disabled:cursor-not-allowed transition-all"
            >
              {isEvaluatorProcessing ? (
                <Loader2 className="h-4 w-4 animate-spin text-primary" />
              ) : (
                <Activity className="h-4 w-4" />
              )}
              Accuracy Evaluator
            </TabsTrigger>
          </TabsList>

          <div className="mt-6 rounded-2xl border border-border bg-card p-6 shadow-soft sm:p-8">
            <TabsContent value="solver" className="m-0">
              <RfpSolver onProcessingChange={setIsSolverProcessing} />
            </TabsContent>
            <TabsContent value="kb" className="m-0">
              <KnowledgeBase onSyncStateChange={setIsKbSyncing} />
            </TabsContent>
            <TabsContent value="evaluator" className="m-0">
              <AccuracyEvaluator onProcessingChange={setIsEvaluatorProcessing} />
            </TabsContent>
          </div>
        </Tabs>
      </main>
    </div>
  );
}
