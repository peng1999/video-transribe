import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import { MantineProvider, AppShell, Group, Anchor } from "@mantine/core";
import "@mantine/core/styles.css";
import App from "./App";
import History from "./pages/History";

const client = new QueryClient();

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <QueryClientProvider client={client}>
      <MantineProvider defaultColorScheme="light">
        <BrowserRouter>
          <AppShell header={{ height: 60 }} padding="md">
            <AppShell.Header>
              <Group h="100%" px="md">
                <Anchor component={Link} to="/">
                  首页
                </Anchor>
                <Anchor component={Link} to="/history">
                  历史记录
                </Anchor>
              </Group>
            </AppShell.Header>
            <AppShell.Main>
              <Routes>
                <Route path="/" element={<App />} />
                <Route path="/history" element={<History />} />
              </Routes>
            </AppShell.Main>
          </AppShell>
        </BrowserRouter>
      </MantineProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);
