import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@/index.css";
import App from "@/App";
const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 60000, refetchOnWindowFocus: false } } });
const bootstrap = document.getElementById("hubaal-bootstrap");
async function start() {
 let business;
 if(bootstrap) business=JSON.parse(bootstrap.textContent);
 else { const response=await fetch('/api/public/site-bootstrap?lang='+encodeURIComponent(new URLSearchParams(location.search).get('lang')||'en')); if(!response.ok)throw Error(); business=await response.json(); }
 ReactDOM.createRoot(document.getElementById("root")).render(<React.StrictMode><QueryClientProvider client={queryClient}><App business={business} /></QueryClientProvider></React.StrictMode>);
}
start().catch(() => { document.getElementById('root').textContent = 'The website could not load. Please refresh the page or try again shortly.'; });
