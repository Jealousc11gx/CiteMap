import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { AlertCircle, RefreshCcw } from "lucide-react";

interface ErrorAlertProps {
  title?: string;
  message: string;
  suggestion?: string;
  onRetry?: () => void;
}

export function ErrorAlert({ title = "操作失败", message, suggestion, onRetry }: ErrorAlertProps) {
  return (
    <Alert variant="destructive" className="mb-3 border-destructive/20">
      <AlertCircle className="h-4 w-4" />
      <AlertDescription className="space-y-1">
        <p className="font-medium">{title}</p>
        <p>{message}</p>
        {suggestion && <p className="text-xs opacity-90">{suggestion}</p>}
        {onRetry && (
          <Button variant="outline" size="sm" className="mt-2" onClick={onRetry}>
            <RefreshCcw className="mr-1 h-3 w-3" />
            重试
          </Button>
        )}
      </AlertDescription>
    </Alert>
  );
}
