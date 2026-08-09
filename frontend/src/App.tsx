import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import DashboardPage from "./pages/DashboardPage";

import JarvisNavbar from "@/components/JarvisNavbar";
import JarvisOverlay from "@/components/JarvisOverlay";

import StartupPage from "./pages/StartupPage";
import Index from "./pages/Index";
import AssistantPage from "./pages/AssistantPage";
import NotesPage from "./pages/NotesPage";
import CalendarPage from "./pages/CalendarPage";
import TasksPage from "./pages/TasksPage";
import AboutPage from "./pages/AboutPage";
import NotFound from "./pages/NotFound";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />

      <BrowserRouter>

        {/* floating jarvis */}
        <JarvisOverlay />

        {/* navbar */}
        <JarvisNavbar />

        <Routes>

          {/* boot */}
          <Route path="/startup" element={<StartupPage />} />

          {/* dashboard */}
          <Route path="/" element={<Index />} />

          {/* pages */}
          <Route path="/assistant" element={<AssistantPage />} />
          <Route path="/notes" element={<NotesPage />} />
          <Route path="/calendar" element={<CalendarPage />} />
          <Route path="/tasks" element={<TasksPage />} />
          <Route path="/about" element={<AboutPage />} />
          <Route path="/dashboard" element={<DashboardPage />} />

          <Route path="*" element={<NotFound />} />

        </Routes>

      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;