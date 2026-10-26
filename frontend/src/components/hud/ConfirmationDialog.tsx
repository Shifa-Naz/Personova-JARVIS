import { useEffect, useState } from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import type { ConfirmationInfo } from "@/features/assistant/types";

interface Props {
  confirmation: ConfirmationInfo | null;
  onDecide: (decision: "confirm" | "cancel") => void;
}

const ConfirmationDialog = ({ confirmation, onDecide }: Props) => {
  const [secondsLeft, setSecondsLeft] = useState(0);

  useEffect(() => {
    if (!confirmation) return;
    const tick = () => setSecondsLeft(Math.max(0, Math.round(confirmation.expires_at - Date.now() / 1000)));
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, [confirmation]);

  if (!confirmation) return null;
  const destructive = confirmation.permission === "DESTRUCTIVE";
  const isOffer = confirmation.kind === "offer";
  const title = isOffer ? "Should I go ahead?" : destructive ? "This can't be undone" : "Check before I do this";
  const accent = destructive ? "bg-jarvis-red" : "bg-jarvis-ember";

  return (
    <AlertDialog open onOpenChange={(open) => !open && onDecide("cancel")}>
      <AlertDialogContent className="overflow-hidden border-border bg-card p-0 sm:rounded-xl">
        <div className={`h-1 w-full ${accent}`} aria-hidden />
        <div className="space-y-4 p-6">
          <AlertDialogHeader>
            <AlertDialogTitle className="font-display text-xl">{title}</AlertDialogTitle>
            <AlertDialogDescription className="text-base leading-relaxed text-foreground/90">
              {confirmation.summary}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <p className="text-sm text-muted-foreground">
            {secondsLeft > 0 ? `You can also say “yes” or “no”. This expires in ${secondsLeft} seconds.` : "This request expired."}
          </p>
          <AlertDialogFooter className="gap-2 sm:gap-2">
            <AlertDialogCancel onClick={() => onDecide("cancel")} className="mt-0 min-h-11 border-border bg-transparent">
              {isOffer ? "No thanks" : "Cancel"}
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={() => onDecide("confirm")}
              disabled={secondsLeft === 0}
              className={`min-h-11 ${destructive ? "bg-jarvis-red text-background hover:bg-jarvis-red/90" : "bg-jarvis-ember text-background hover:bg-jarvis-ember/90"}`}
            >
              {isOffer ? "Yes, go ahead" : destructive ? "Yes, do it" : "Confirm"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </div>
      </AlertDialogContent>
    </AlertDialog>
  );
};

export default ConfirmationDialog;
