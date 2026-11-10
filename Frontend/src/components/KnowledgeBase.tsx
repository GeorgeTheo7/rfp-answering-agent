import { useState, useEffect } from "react";
import { API_BASE } from "@/lib/api";
import { motion } from "framer-motion";
import { RefreshCw, Trash2, FileText, CheckCircle2, Loader2 } from "lucide-react";
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

interface KbDoc {
  id: string;
  name: string;
  status: "Indexed" | "Processing";
}

interface KnowledgeBaseProps {
  onSyncStateChange?: (isSyncing: boolean) => void;
}

export function KnowledgeBase({ onSyncStateChange }: KnowledgeBaseProps) {
  const [files, setFiles] = useState<File[]>([]);
  const [docs, setDocs] = useState<KbDoc[]>([]);

  const [isSyncing, setIsSyncing] = useState(false);
  const [isInitialLoading, setIsInitialLoading] = useState(true);

  const fetchDocuments = async (isInit = false) => {
    try {
      const res = await fetch(`${API_BASE}/documents`);

      if (res.ok) {
        const data = await res.json();
        const formattedDocs: KbDoc[] = data.documents.map((filename: string) => ({
          id: filename,
          name: filename,
          status: "Indexed",
        }));
        setDocs(formattedDocs);

        if (isInit) setIsInitialLoading(false);
      } else {
        if (isInit) setTimeout(() => fetchDocuments(true), 3000);
      }
    } catch (error) {
      if (isInit) {
        setTimeout(() => fetchDocuments(true), 3000);
      } else {
        console.error("Error during the installation of the files:", error);
      }
    }
  };

  useEffect(() => {
    fetchDocuments(true);
  }, []);

  const handleSync = async () => {
    if (files.length === 0) return;

    setIsSyncing(true);
    if (onSyncStateChange) onSyncStateChange(true);

    const formData = new FormData();
    files.forEach((file) => {
      formData.append("files", file);
    });

    try {
      const res = await fetch(`${API_BASE}/documents/upload`, {
        method: "POST",
        body: formData,
      });

      if (res.ok) {
        setFiles([]);
        fetchDocuments();
      } else {
        const errorData = await res.json().catch(() => null);
        alert(errorData?.detail || "There was a problem uploading.");
      }
    } catch (error) {
      console.error(error);
      alert("Could not reach the server.");
    } finally {
      setIsSyncing(false);
      if (onSyncStateChange) onSyncStateChange(false);
    }
  };

  const handleDelete = async (filename: string) => {
    if (
      !confirm(
        `Are you sure you want to delete the file with title: ${filename} from the database;`,
      )
    )
      return;

    try {
      const res = await fetch(`${API_BASE}/documents/${filename}`, {
        method: "DELETE",
      });

      if (res.ok) {
        fetchDocuments();
      }
    } catch (error) {
      console.error(error);
      alert("Delete failed.");
    }
  };

  const handleDeleteAll = async () => {
    if (!confirm("Are you sure you want to Delete all the files?")) return;

    try {
      const res = await fetch(`${API_BASE}/documents/all`, {
        method: "DELETE",
      });

      if (res.ok) {
        fetchDocuments();
      } else {
        alert("Failed to delete all documents.");
      }
    } catch (error) {
      console.error(error);
      alert("Server communication error.");
    }
  };

  if (isInitialLoading || isSyncing) {
    return (
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="flex flex-col items-center justify-center py-24 px-6 w-full rounded-xl border border-border bg-surface shadow-soft"
      >
        <div className="relative mb-6 flex h-24 w-24 items-center justify-center">
          <motion.div
            className="absolute inset-0 rounded-full border-2 border-primary/20"
            animate={{ scale: [1, 1.25, 1], opacity: [0.8, 0, 0.8] }}
            transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
          />
          <div className="relative flex h-16 w-16 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-glow">
            <Loader2 className="h-8 w-8 animate-spin" />
          </div>
        </div>

        <h2 className="text-xl font-bold tracking-tight text-foreground text-center">
          {isInitialLoading
            ? "Server is starting and analyzing local files..."
            : "Waiting for the File/Files to get analyzed..."}
        </h2>
        <p className="mt-3 text-sm text-muted-foreground text-center max-w-sm">
          {isInitialLoading
            ? "Please wait while the AI agent parses the documents in your local data folder and updates the Vector Database. This might take a few moments depending on the amount of files."
            : "Please wait while the AI agent parses the documents, extracts text, and updates the Vector Database. This might take a few moments."}
        </p>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="grid gap-6 lg:grid-cols-5"
    >
      <section className="space-y-4 lg:col-span-2">
        <div>
          <h2 className="text-base font-semibold tracking-tight text-foreground">
            Upload new documents
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Add internal company PDFs and previous RFP Excel files to power AI answers.
          </p>
        </div>

        {/* [UPDATED] DropZone also accepts .xlsx, .xlsm */}
        <DropZone
          title="Drop internal documents here"
          subtitle="PDF, .xlsx, .xlsm — policies, previous RFPs, datasheets"
          accept=".pdf,.xlsx,.xlsm"
          files={files}
          onFilesChange={setFiles}
        />
        <Button onClick={handleSync} disabled={files.length === 0} className="w-full gap-2">
          <RefreshCw className="h-4 w-4" />
          Process & Sync to Vector DB
        </Button>
      </section>

      <section className="space-y-4 lg:col-span-3">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold tracking-tight text-foreground">
              Indexed documents
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {docs.length} documents in your knowledge base
            </p>
          </div>

          <div className="flex items-center gap-3">
            {docs.length > 0 && (
              <Button
                variant="destructive"
                size="sm"
                onClick={handleDeleteAll}
                className="h-8 text-xs gap-1.5"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Remove All
              </Button>
            )}
          </div>
        </div>

        <div className="overflow-hidden rounded-xl border border-border bg-surface shadow-soft">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/60 hover:bg-muted/60">
                <TableHead>Document Name</TableHead>
                <TableHead className="w-28">Status</TableHead>
                <TableHead className="w-16 text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {docs.map((doc) => (
                <TableRow key={doc.id} className="transition-colors hover:bg-accent/40">
                  <TableCell>
                    <div className="flex items-center gap-2.5">
                      <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary/10 text-primary">
                        <FileText className="h-4 w-4" />
                      </div>
                      <div className="flex flex-col">
                        <span className="text-sm font-medium text-foreground">{doc.name}</span>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell>
                    <span className="inline-flex items-center gap-1 text-xs font-medium text-success">
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      {doc.status}
                    </span>
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => handleDelete(doc.id)}
                      className="h-8 w-8 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                      aria-label="Delete document"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {docs.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={3}
                    className="py-10 text-center text-sm text-muted-foreground"
                  >
                    No documents indexed yet. Upload files to start.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </section>
    </motion.div>
  );
}
