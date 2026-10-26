import { useEffect } from "react";
import { Link, useLocation } from "react-router-dom";

const NotFound = () => {
  const location = useLocation();

  useEffect(() => {
    console.warn("404: no route for", location.pathname);
  }, [location.pathname]);

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="max-w-md text-center">
        <p className="tabular font-display text-7xl font-semibold text-primary">404</p>
        <h1 className="mt-4 text-2xl font-semibold text-foreground">There's no page at {location.pathname}</h1>
        <p className="mt-2 text-muted-foreground">It may have moved. The dashboard has everything else.</p>
        <Link to="/" className="mt-6 inline-flex min-h-11 items-center rounded-xl bg-primary px-6 font-medium text-primary-foreground">
          Go to the dashboard
        </Link>
      </div>
    </div>
  );
};

export default NotFound;
