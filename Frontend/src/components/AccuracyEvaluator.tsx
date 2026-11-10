import { useState, useEffect } from "react";
import { API_BASE } from "@/lib/api";
import { motion, AnimatePresence } from "framer-motion";
import { Activity, Loader2, Bot, AlertCircle, Download, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { DropZone } from "./DropZone";

type EvalStep = "upload" | "processing" | "results";

interface EvalRow {
  id: string;
  question: string;
  expected: string;
  generated: string;
  score: number;
  reasoning: string;
}

interface AccuracyEvaluatorProps {
  onProcessingChange?: (isProcessing: boolean) => void;
}

export function AccuracyEvaluator({ onProcessingChange }: AccuracyEvaluatorProps) {
  // Restore data from sessionStorage
  const [step, setStep] = useState<EvalStep>(() => {
    const savedStep = sessionStorage.getItem("eval_step");
    if (savedStep === "results") return "results";
    return "upload";
  });

  const [files, setFiles] = useState<File[]>([]);

  const [results, setResults] = useState<EvalRow[]>(() => {
    const savedData = sessionStorage.getItem("eval_results");
    if (savedData) {
      try {
        return JSON.parse(savedData);
      } catch (e) {
        return [];
      }
    }
    return [];
  });

  const [overallAccuracy, setOverallAccuracy] = useState<number>(() => {
    return Number(sessionStorage.getItem("eval_accuracy")) || 0;
  });

  const [needsReviewCount, setNeedsReviewCount] = useState<number>(() => {
    return Number(sessionStorage.getItem("eval_needsReview")) || 0;
  });

  const [excelBase64, setExcelBase64] = useState<string>(() => {
    return sessionStorage.getItem("eval_excelBase64") || "";
  });

  const [filename, setFilename] = useState<string>(() => {
    return sessionStorage.getItem("eval_filename") || "";
  });

  const [selectedModel, setSelectedModel] = useState(() => {
    return sessionStorage.getItem("eval_model") || "gpt-6-luna";
  });

  const [isOpenAiAvailable, setIsOpenAiAvailable] = useState(true);

  // Save to sessionStorage whenever the data changes
  useEffect(() => {
    sessionStorage.setItem("eval_step", step);
    sessionStorage.setItem("eval_results", JSON.stringify(results));
    sessionStorage.setItem("eval_accuracy", overallAccuracy.toString());
    sessionStorage.setItem("eval_needsReview", needsReviewCount.toString());
    sessionStorage.setItem("eval_excelBase64", excelBase64);
    sessionStorage.setItem("eval_filename", filename);
    sessionStorage.setItem("eval_model", selectedModel);
  }, [step, results, overallAccuracy, needsReviewCount, excelBase64, filename, selectedModel]);

  // Check whether the OpenAI API key is available
  useEffect(() => {
    fetch(`${API_BASE}/providers/status`)
      .then((res) => res.json())
      .then((data) => setIsOpenAiAvailable(data.openai))
      .catch(() => setIsOpenAiAvailable(false));
  }, []);

  const AI_MODELS = [
    { id: "gpt-4o-mini", name: "GPT-4o Mini", cost: "Low", speed: "Fast" },
    { id: "gpt-5-mini", name: "GPT-5 Mini", cost: "Medium", speed: "Fast" },
    { id: "gpt-6-luna", name: "GPT-6 Luna", cost: "Low", speed: "Medium" },
  ];

  const handleEvaluate = async () => {
    if (files.length === 0) return;

    setStep("processing");
    if (onProcessingChange) onProcessingChange(true);

    const formData = new FormData();
    formData.append("file", files[0]);
    formData.append("model", selectedModel);

    try {
      const response = await fetch(`${API_BASE}/rfp/evaluate`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Error evaluating accuracy.");
      }

      const data = await response.json();
      setResults(data.results);
      setOverallAccuracy(data.overall_accuracy);
      setNeedsReviewCount(data.needs_review_count ?? 0);
      setExcelBase64(data.excel_base64);
      setFilename(data.filename);
      setStep("results");
    } catch (error: unknown) {
      console.error(error);
      alert(error instanceof Error ? error.message : String(error));
      setStep("upload");
    } finally {
      if (onProcessingChange) onProcessingChange(false);
    }
  };

  const handleDownload = () => {
    if (!excelBase64) return;
    const a = document.createElement("a");
    a.href =
      "data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64," +
      excelBase64;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  const reset = () => {
    setStep("upload");
    setFiles([]);
    setResults([]);
    setOverallAccuracy(0);
    setNeedsReviewCount(0);
    setExcelBase64("");
    sessionStorage.removeItem("eval_step");
    sessionStorage.removeItem("eval_results");
    sessionStorage.removeItem("eval_accuracy");
    sessionStorage.removeItem("eval_needsReview");
    sessionStorage.removeItem("eval_excelBase64");
    sessionStorage.removeItem("eval_filename");
  };

  const getScoreColor = (score: number) => {
    if (score >= 90) return "text-emerald-600 bg-emerald-50 ring-emerald-500/20";
    if (score >= 60) return "text-amber-600 bg-amber-50 ring-amber-500/20";
    return "text-red-600 bg-red-50 ring-red-500/20";
  };

  return (
    <div className="relative">
      <AnimatePresence mode="wait">
        {step === "upload" && (
          <motion.div
            key="upload"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            className="space-y-6"
          >
            <div>
              <h2 className="text-xl font-semibold tracking-tight text-foreground">
                LLM Accuracy Evaluator
              </h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Upload an Excel file containing a <strong>"Question"</strong> column and an{" "}
                <strong>"Expected Answer"</strong> (or Ground Truth) column. The system will
                generate answers and an LLM-Judge will score them.
              </p>
            </div>

            <DropZone
              title="Drop your Ground Truth Excel here"
              subtitle="Requires .xlsx or .xlsm files"
              accept=".xlsx,.xlsm"
              files={files}
              onFilesChange={setFiles}
            />

            <div className="bg-muted/30 p-4 rounded-xl border border-border mt-4">
              <label className="block text-sm font-medium text-foreground mb-2 flex items-center gap-2">
                <Bot className="h-4 w-4 text-primary" />
                Agent Model (judge is fixed: gpt-6-luna)
              </label>
              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                disabled={!isOpenAiAvailable}
                className={`w-full h-10 rounded-md border border-input px-3 py-2 text-sm focus:ring-2 focus:ring-primary/50 outline-none transition-all shadow-sm cursor-pointer ${!isOpenAiAvailable ? "bg-muted text-muted-foreground italic cursor-not-allowed" : "bg-background text-foreground"}`}
              >
                {AI_MODELS.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}{" "}
                    {isOpenAiAvailable
                      ? `— (Cost: ${m.cost} | ${m.speed})`
                      : "— 🔒 Missing OpenAI API Key"}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex justify-end mt-4">
              <Button
                size="lg"
                onClick={handleEvaluate}
                disabled={files.length === 0 || !isOpenAiAvailable}
                className="gap-2 shadow-soft"
              >
                <Activity className="h-4 w-4" />
                Run Evaluation
              </Button>
            </div>
          </motion.div>
        )}

        {step === "processing" && (
          <motion.div
            key="processing"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex flex-col items-center justify-center py-16"
          >
            <div className="relative mb-6 flex h-20 w-20 items-center justify-center">
              <motion.div
                className="absolute inset-0 rounded-full border-2 border-primary/20"
                animate={{ scale: [1, 1.2, 1], opacity: [0.6, 0, 0.6] }}
                transition={{ duration: 1.8, repeat: Infinity }}
              />
              <div className="relative flex h-16 w-16 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-glow">
                <Bot className="h-8 w-8" />
              </div>
            </div>
            <p className="text-center text-base font-semibold text-foreground">
              Generating answers & running LLM Judge...
            </p>
            <p className="mt-2 text-sm text-muted-foreground text-center max-w-sm">
              This process takes longer because the AI first answers the questions using RAG, and
              then a separate LLM evaluates the semantics of each answer.
            </p>
            <div className="mt-8 flex items-center justify-center gap-2 text-primary">
              <Loader2 className="h-5 w-5 animate-spin" />
            </div>
          </motion.div>
        )}

        {step === "results" && (
          <motion.div
            key="results"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            className="space-y-6"
          >
            <div className="flex flex-wrap items-center justify-between gap-3 bg-surface border border-border p-5 rounded-xl shadow-sm">
              <div>
                <h2 className="text-2xl font-bold tracking-tight text-foreground">
                  Overall Accuracy
                </h2>
                <p className="text-sm text-muted-foreground">Based on LLM semantic similarity</p>
                {needsReviewCount > 0 && (
                  <p className="text-sm text-amber-600">
                    {needsReviewCount} {needsReviewCount === 1 ? "answer needs" : "answers need"}{" "}
                    review (scored normally)
                  </p>
                )}
              </div>
              <div className="flex items-center gap-6">
                <Button variant="outline" size="sm" onClick={reset} className="gap-2">
                  <RotateCcw className="h-3.5 w-3.5" />
                  Start over
                </Button>
                <div className="text-right">
                  <span
                    className={`text-4xl font-extrabold ${overallAccuracy >= 90 ? "text-emerald-500" : overallAccuracy >= 70 ? "text-amber-500" : "text-red-500"}`}
                  >
                    {overallAccuracy}%
                  </span>
                </div>
              </div>
            </div>

            <div className="overflow-hidden rounded-xl border border-border bg-surface shadow-soft">
              <div className="max-h-[500px] overflow-auto">
                <Table>
                  <TableHeader className="sticky top-0 z-10 bg-muted/90 backdrop-blur">
                    <TableRow>
                      <TableHead className="w-16">ID</TableHead>
                      <TableHead className="w-1/4">Question</TableHead>
                      <TableHead className="w-1/4">Generated Answer (RAG)</TableHead>
                      <TableHead className="w-1/4">Expected Answer</TableHead>
                      <TableHead className="w-1/4">LLM Evaluation</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {results.map((row, index) => (
                      <TableRow key={index} className="align-top hover:bg-accent/40">
                        <TableCell className="font-mono text-xs text-muted-foreground">
                          {row.id}
                        </TableCell>
                        <TableCell className="text-sm font-medium">{row.question}</TableCell>
                        <TableCell className="text-sm">
                          {row.generated.includes("Couldnt be able to find") ? (
                            <span className="text-red-500 font-medium flex items-center gap-1">
                              <AlertCircle className="h-4 w-4" /> Missing Info
                            </span>
                          ) : (
                            row.generated
                          )}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {row.expected}
                        </TableCell>
                        <TableCell>
                          <div className="flex flex-col gap-2">
                            <span
                              className={`inline-flex w-fit items-center rounded-md px-2 py-1 text-xs font-bold ring-1 ring-inset ${getScoreColor(row.score)}`}
                            >
                              Score: {row.score}/100
                            </span>
                            <p className="text-xs text-muted-foreground italic">{row.reasoning}</p>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>

            <div className="flex justify-end mt-4">
              <Button size="lg" onClick={handleDownload} className="gap-2 shadow-soft">
                <Download className="h-4 w-4" />
                Download Evaluated Excel
              </Button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
