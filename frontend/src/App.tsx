import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import ConfirmationDialog from "@/components/hud/ConfirmationDialog";
import JarvisNavbar from "@/components/JarvisNavbar";
import JarvisOverlay from "@/components/JarvisOverlay";
import { AssistantProvider } from "@/features/assistant/AssistantProvider";
import { useAssistant } from "@/features/assistant/context";

import AboutPage from "./pages/AboutPage";
import AssistantPage from "./pages/AssistantPage";
import CalendarPage from "./pages/CalendarPage";
import Index from "./pages/Index";
import NotesPage from "./pages/NotesPage";
import NotFound from "./pages/NotFound";
import StartupPage from "./pages/StartupPage";
import TasksPage from "./pages/TasksPage";

/** Confirmations can arrive from any page (voice works everywhere), so the dialog is global. */
const GlobalConfirmation = () => {
  const { state, decide } = useAssistant();
  return <ConfirmationDialog confirmation={state.confirmation} onDecide={(d) => void decide(d)} />;
};

const App = () => (
  <TooltipProvider>
    <Toaster />
    <Sonner />
    <BrowserRouter>
      <AssistantProvider>
        <JarvisNavbar />
        <main>
          <Routes>
            <Route path="/startup" element={<StartupPage />} />
            <Route path="/" element={<Index />} />
            <Route path="/dashboard" element={<Navigate to="/" replace />} />
            <Route path="/assistant" element={<AssistantPage />} />
            <Route path="/notes" element={<NotesPage />} />
            <Route path="/calendar" element={<CalendarPage />} />
            <Route path="/tasks" element={<TasksPage />} />
            <Route path="/about" element={<AboutPage />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </main>
        <JarvisOverlay />
        <GlobalConfirmation />
      </AssistantProvider>
    </BrowserRouter>
  </TooltipProvider>
);

export default App;
