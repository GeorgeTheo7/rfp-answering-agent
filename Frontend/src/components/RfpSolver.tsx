import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Zap, Loader2, Download, CheckCircle2, RotateCcw, Bot } from "lucide-react";
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
import { CategoryBadge, type Category } from "./CategoryBadge";

type Step = "upload" | "processing" | "results";

type AnswerStatus = "answered" | "not_found" | "needs_review" | "error";

interface QuestionRow {
  id: string;
  category: Category;
  question: string;
  answer: string;
  sources: string[];
  conflicts: string; // [NEW] conflicts field
  review_note?: string; // why the agent doubts a needs_review answer; cleared on edit
  status?: AnswerStatus; // missing in rows saved in sessionStorage before this field existed
}

const ANSWER_STATUS_CLASSES: Partial<Record<AnswerStatus, string>> = {
  not_found: "border-destructive/50 text-destructive font-medium",
  error: "border-destructive/50 text-destructive font-medium",
  needs_review: "border-amber-500/50 text-amber-900 font-medium",
};

interface RfpSolverProps {
  onProcessingChange?: (isProcessing: boolean) => void;
}

export function RfpSolver({ onProcessingChange }: RfpSolverProps) {
  const [step, setStep] = useState<Step>(() => {
    const savedStep = sessionStorage.getItem("rfp_step");
    if (savedStep === "results") return "results";
    return "upload";
  });

  const [files, setFiles] = useState<File[]>([]);

  const [tableData, setTableData] = useState<QuestionRow[]>(() => {
    const savedData = sessionStorage.getItem("rfp_tableData");
    if (savedData) {
      try {
        return JSON.parse(savedData);
      } catch (e) {
        return [];
      }
    }
    return [];
  });

  const [downloadFilename, setDownloadFilename] = useState<string>(() => {
    return sessionStorage.getItem("rfp_filename") || "Answered_RFP.xlsx";
  });

  const [isDownloading, setIsDownloading] = useState(false);

  const [selectedModel, setSelectedModel] = useState(() => {
    return sessionStorage.getItem("rfp_model") || "gpt-4o-mini";
  });

  const [isOpenAiAvailable, setIsOpenAiAvailable] = useState(true);

  useEffect(() => {
    sessionStorage.setItem("rfp_step", step);
    sessionStorage.setItem("rfp_tableData", JSON.stringify(tableData));
    sessionStorage.setItem("rfp_filename", downloadFilename);
    sessionStorage.setItem("rfp_model", selectedModel);
  }, [step, tableData, downloadFilename, selectedModel]);

  useEffect(() => {
    fetch("http://localhost:8000/api/providers/status")
      .then((res) => res.json())
      .then((data) => setIsOpenAiAvailable(data.openai))
      .catch(() => setIsOpenAiAvailable(false));
  }, []);

  const AI_MODELS = [
    { id: "gpt-4o-mini", name: "GPT-4o Mini", cost: "Low", speed: "Fast" },
    { id: "gpt-5-mini", name: "GPT-5 Mini", cost: "Medium", speed: "Fast" },
  ];

  const handleAnalyze = async () => {
    if (files.length === 0) return;

    setStep("processing");
    if (onProcessingChange) onProcessingChange(true);

    const formData = new FormData();
    formData.append("file", files[0]);
    formData.append("model", selectedModel);

    try {
      const response = await fetch("http://localhost:8000/api/rfp/analyze", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "The API returned an error!");
      }

      const data = await response.json();
      setTableData(data.preview_data);
      setDownloadFilename(data.filename);
      setStep("results");
    } catch (error: unknown) {
      console.error("Analysis error:", error);
      alert(error instanceof Error ? error.message : String(error));
      setStep("upload");
    } finally {
      if (onProcessingChange) onProcessingChange(false);
    }
  };

  const handleDownloadEdits = async () => {
    setIsDownloading(true);
    try {
      const response = await fetch("http://localhost:8000/api/rfp/export_edits", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rows: tableData, filename: downloadFilename }),
      });
      if (!response.ok) throw new Error("Export failed.");
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = downloadFilename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      alert("Failed to download the updated file.");
    } finally {
      setIsDownloading(false);
    }
  };

  const reset = () => {
    setStep("upload");
    setFiles([]);
    setTableData([]);

    sessionStorage.removeItem("rfp_step");
    sessionStorage.removeItem("rfp_tableData");
    sessionStorage.removeItem("rfp_filename");
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
            transition={{ duration: 0.25 }}
            className="space-y-6"
          >
            <div>
              <h2 className="text-xl font-semibold tracking-tight text-foreground">
                Upload an RFP
              </h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Our AI Agents will extract every question and draft answers from your knowledge
                base.
              </p>
            </div>

            <DropZone
              title="Drag and drop the client's RFP"
              subtitle="Supports .xlsx, .xlsm, .pdf — up to 50MB"
              accept=".xlsx,.xlsm,.pdf"
              files={files}
              onFilesChange={setFiles}
            />

            <div className="bg-muted/30 p-4 rounded-xl border border-border mt-4">
              <label className="block text-sm font-medium text-foreground mb-2 flex items-center gap-2">
                <Bot className="h-4 w-4 text-primary" />
                Select OpenAI Model (Engine)
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
                onClick={handleAnalyze}
                disabled={files.length === 0 || !isOpenAiAvailable}
                className="gap-2 shadow-soft"
              >
                <Zap className="h-4 w-4" />
                Analyze & Answer
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
            transition={{ duration: 0.25 }}
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
              Our Agents are processing the document...
            </p>
            <div className="mt-8 flex items-center justify-center gap-2 text-primary">
              <Loader2 className="h-5 w-5 animate-spin" />
              <span className="text-sm font-medium">Drafting answers...</span>
            </div>
          </motion.div>
        )}

        {step === "results" && (
          <motion.div
            key="results"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.3 }}
            className="space-y-6"
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-xl font-semibold tracking-tight text-foreground">
                  Drafted Answers
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  {tableData.length} questions extracted •{" "}
                  <strong>Edit the answers below before exporting.</strong>
                </p>
              </div>
              <Button variant="outline" size="sm" onClick={reset} className="gap-2">
                <RotateCcw className="h-3.5 w-3.5" />
                Start over
              </Button>
            </div>

            <div className="overflow-hidden rounded-xl border border-border bg-surface shadow-soft">
              <div className="max-h-[550px] overflow-auto">
                <Table>
                  <TableHeader className="sticky top-0 z-10 bg-muted/60 backdrop-blur">
                    <TableRow className="hover:bg-transparent">
                      <TableHead className="w-16">ID</TableHead>
                      <TableHead className="w-24">Category</TableHead>
                      <TableHead className="min-w-[200px]">Question</TableHead>
                      <TableHead className="min-w-[380px]">Edit AI Answer</TableHead>
                      <TableHead className="min-w-[250px]">Conflicts Found</TableHead>
                      <TableHead className="min-w-[150px]">Sources Cited</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {tableData.map((row, index) => (
                      <TableRow
                        key={row.id || index}
                        className="align-top transition-colors hover:bg-accent/40"
                      >
                        <TableCell className="font-mono text-xs text-muted-foreground">
                          {row.id}
                        </TableCell>
                        <TableCell>
                          <CategoryBadge category={(row.category as Category) || "Product"} />
                        </TableCell>
                        <TableCell className="text-sm font-medium text-foreground">
                          {row.question}
                        </TableCell>
                        <TableCell className="min-w-[320px] p-2">
                          <textarea
                            className={`w-full min-h-[90px] p-3 text-sm bg-background border rounded-md outline-none transition-colors focus:ring-2 focus:ring-primary/50 resize-y shadow-sm ${
                              (row.status && ANSWER_STATUS_CLASSES[row.status]) ||
                              "border-input text-foreground"
                            }`}
                            value={row.answer}
                            onChange={(e) => {
                              const newData = [...tableData];
                              newData[index].answer = e.target.value;
                              newData[index].status = "answered"; // a human took over this row
                              newData[index].review_note = "";
                              setTableData(newData);
                            }}
                          />
                          {row.review_note && (
                            <p
                              className="mt-1 rounded-md border border-amber-500/50 bg-amber-50/50 p-2 text-xs text-amber-900"
                              title="Why this answer needs review"
                            >
                              Review: {row.review_note}
                            </p>
                          )}
                        </TableCell>
                        <TableCell className="min-w-[250px] p-2">
                          {row.conflicts ? (
                            <textarea
                              className="w-full min-h-[90px] p-3 text-sm bg-amber-50/50 border border-amber-500/50 rounded-md outline-none focus:ring-2 focus:ring-amber-500/50 resize-y text-amber-900 shadow-sm transition-colors"
                              value={row.conflicts}
                              onChange={(e) => {
                                const newData = [...tableData];
                                newData[index].conflicts = e.target.value;
                                setTableData(newData);
                              }}
                              title="Possible conflicting information found"
                            />
                          ) : (
                            <div className="flex h-full items-center justify-center p-3 text-xs italic text-muted-foreground bg-muted/20 rounded-md border border-dashed border-border">
                              No conflicts detected
                            </div>
                          )}
                        </TableCell>
                        <TableCell>
                          <div className="flex flex-wrap gap-1">
                            {row.sources.map(
                              (s, i) =>
                                s.trim() && (
                                  <span
                                    key={i}
                                    className="inline-flex items-center rounded-md bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground ring-1 ring-inset ring-border"
                                  >
                                    {s}
                                  </span>
                                ),
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>

            <div className="flex flex-col items-start gap-4 rounded-xl border border-success/30 bg-success/5 p-5 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-start gap-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-success text-success-foreground">
                  <CheckCircle2 className="h-5 w-5" />
                </div>
                <div>
                  <p className="font-semibold text-foreground">Analysis Completed Successfully!</p>
                  <p className="text-sm text-muted-foreground">
                    Review your edits. The downloaded Excel will contain your exact text.
                  </p>
                </div>
              </div>
              <Button
                size="lg"
                onClick={handleDownloadEdits}
                disabled={isDownloading}
                className="gap-2 shadow-soft min-w-[240px]"
              >
                {isDownloading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Download className="h-4 w-4" />
                )}
                {isDownloading ? "Generating Excel..." : "Download Edited Excel"}
              </Button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
