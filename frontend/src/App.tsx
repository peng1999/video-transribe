import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Alert,
  Badge,
  Button,
  Card,
  Container,
  Grid,
  Group,
  Loader,
  Select,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { IconAlertCircle } from "@tabler/icons-react";
import {
  createJob,
  subscribeJob,
  JobStage,
  getJob,
  regenerateJob,
  Provider,
  BailianModel,
} from "./api";

interface ProgressEvent {
  stage?: JobStage;
  message?: string;
  words?: number;
  chunk?: string;
  raw_text?: string;
  formatted_text?: string;
  error?: string;
}

type DisplayStage = {
  label: string;
  key: JobStage;
};

const stages: DisplayStage[] = [
  { key: "downloading", label: "下载音频" },
  { key: "transcribing", label: "转录中" },
  { key: "formatting", label: "整理中" },
  { key: "done", label: "完成" },
  { key: "error", label: "失败" },
];

type ProviderOptionValue = "bailian-qwen3" | "bailian-fun-asr" | "openai";
type ProviderOption = {
  value: ProviderOptionValue;
  provider: Provider;
  model?: BailianModel;
  label: string;
  badge: string;
};

function getSavedSelection(): ProviderOptionValue {
  if (typeof window === "undefined") return "bailian-qwen3";
  const saved = window.localStorage.getItem("providerSelection");
  if (saved === "bailian-fun-asr" || saved === "openai" || saved === "bailian-qwen3") {
    return saved;
  }
  return "bailian-qwen3";
}

function StageBadge({ active }: { active: boolean }) {
  return (
    <span
      style={{
        display: "inline-block",
        width: 10,
        height: 10,
        borderRadius: "50%",
        background: active ? "#4caf50" : "#ccc",
        marginRight: 6,
      }}
    ></span>
  );
}

export default function App() {
  const [url, setUrl] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [selectedValue, setSelectedValue] = useState<ProviderOptionValue>(() =>
    getSavedSelection(),
  );
  const [provider, setProvider] = useState<Provider>(() => {
    const sel = getSavedSelection();
    return sel === "openai" ? "openai" : "bailian";
  });
  const [stage, setStage] = useState<JobStage | "pending">("pending");
  const [wordCount, setWordCount] = useState(0);
  const [formatted, setFormatted] = useState("");
  const [raw, setRaw] = useState("");
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const stageRef = useRef<JobStage | "pending">("pending");
  const [searchParams] = useSearchParams();

  useEffect(() => {
    return () => {
      console.debug("ws cleanup on unmount");
      wsRef.current?.close();
    };
  }, []);

  const resetView = () => {
    setError(null);
    setFormatted("");
    setRaw("");
    setWordCount(0);
  };

  const handleStreamMessage = (payload: ProgressEvent) => {
    console.debug("ws message");
    if (payload.stage) {
      setStage(payload.stage);
      stageRef.current = payload.stage;
    }
    const currentStage = payload.stage ?? stageRef.current;
    if (payload.words !== undefined) setWordCount(payload.words);
    if (payload.chunk && currentStage === "transcribing")
      setRaw((prev) => prev + payload.chunk);
    if (payload.chunk && currentStage === "formatting")
      setFormatted((prev) => prev + payload.chunk);
    if (payload.raw_text) setRaw(payload.raw_text);
    if (payload.formatted_text) setFormatted(payload.formatted_text);
    if (payload.error) setError(payload.error);
  };

  const connectWebSocket = (id: string) => {
    wsRef.current?.close();
    console.debug("ws connecting", id);
    const ws = subscribeJob(id, handleStreamMessage, (event) => {
      const current = stageRef.current;
      if (
        current === "done" ||
        current === "error" ||
        event?.code === 1000 ||
        event?.code === 1001
      ) {
        console.debug("ws close no reconnect", event?.code, event?.reason);
        return;
      }
      console.debug(
        "ws closed, will reconnect in 1s",
        event?.code,
        event?.reason,
      );
      setTimeout(() => connectWebSocket(id), 1000);
    });
    ws.onopen = () => {
      console.debug("ws open", id);
    };
    ws.onerror = (e) => {
      console.error("ws error", e);
    };
    wsRef.current = ws;
  };

  const startJob = async (e: FormEvent) => {
    e.preventDefault();
    resetView();
    try {
      setProvider(selectedOption.provider);
      const job = await createJob(
        url,
        selectedOption.provider,
        selectedOption.model,
      );
      setJobId(job.id);
      setProvider(job.provider as Provider);
      setSelectedValue(
        deriveOptionValue(job.provider as Provider, job.model as BailianModel | undefined),
      );
      setStage("downloading");
      stageRef.current = "downloading";
      connectWebSocket(job.id);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "创建任务失败");
    }
  };

  const loadJobFromQuery = async (id: string) => {
    resetView();
    setJobId(id);
    try {
      const job = await getJob(id);
      setProvider(job.provider as Provider);
      setSelectedValue(
        deriveOptionValue(job.provider as Provider, job.model as BailianModel | undefined),
      );
      setStage(job.status);
      stageRef.current = job.status;
      setRaw(job.raw_text || "");
      setFormatted(job.formatted_text || "");
      const baseText = job.formatted_text || job.raw_text || "";
      setWordCount(baseText ? baseText.split(/\s+/).filter(Boolean).length : 0);
      if (job.error) setError(job.error);
      if (job.status !== "done" && job.status !== "error") {
        connectWebSocket(id);
      }
    } catch (err) {
      setError("任务不存在或获取失败");
    }
  };

  useEffect(() => {
    const q = searchParams.get("job");
    if (q) {
      loadJobFromQuery(q);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const stageMap = useMemo(
    () => Object.fromEntries(stages.map((s) => [s.key, s.label])),
    [],
  );

  const providerOptions: ProviderOption[] = [
    {
      value: "bailian-qwen3",
      provider: "bailian",
      model: "qwen3-asr-flash-filetrans",
      label: "阿里百炼 qwen3-asr-flash-filetrans",
      badge: "阿里百炼 qwen3-asr-flash-filetrans + DeepSeek",
    },
    {
      value: "bailian-fun-asr",
      provider: "bailian",
      model: "fun-asr",
      label: "阿里百炼 fun-asr",
      badge: "阿里百炼 fun-asr + DeepSeek",
    },
    {
      value: "openai",
      provider: "openai",
      label: "OpenAI gpt-4o-mini-transcribe",
      badge: "OpenAI gpt-4o-mini-transcribe + DeepSeek",
    },
  ];

  const selectedOption = useMemo(
    () => providerOptions.find((opt) => opt.value === selectedValue) || providerOptions[0],
    [selectedValue, providerOptions],
  );

  const providerBadge = selectedOption.badge;

  function deriveOptionValue(
    p: Provider,
    model?: BailianModel,
  ): ProviderOptionValue {
    if (p === "bailian") {
      if (model === "fun-asr") return "bailian-fun-asr";
      return "bailian-qwen3";
    }
    return "openai";
  }

  // persist provider choice for refresh
  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem("providerSelection", selectedValue);
  }, [selectedValue]);

  const isProcessing =
    stage === "downloading" ||
    stage === "transcribing" ||
    stage === "formatting";

  const handleRegenerate = async () => {
    if (!jobId) return;
    if (!raw) {
      setError("暂无原始转录，无法重新整理");
      return;
    }
    setError(null);
    setFormatted("");
    setStage("formatting");
    stageRef.current = "formatting";
    setWordCount(0);
    connectWebSocket(jobId);
    try {
      await regenerateJob(jobId);
    } catch (err: any) {
      setStage("error");
      stageRef.current = "error";
      setError(err?.response?.data?.detail || "重新整理失败");
    }
  };

  return (
    <Container size="lg" py="md">
      <Card withBorder shadow="xs" padding="lg" radius="md">
        <form onSubmit={startJob}>
          <Stack gap="sm">
            <Group justify="space-between" align="flex-end">
              <Title order={3}>Bilibili 文字转录</Title>
              <Badge color="blue" variant="light">
                {providerBadge}
              </Badge>
            </Group>
            <TextInput
              type="url"
              label="视频链接"
              placeholder="输入 bilibili 视频链接"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              required
            />
            <Select
              label="后端提供方"
              data={providerOptions.map((opt) => ({
                value: opt.value,
                label: opt.label,
              }))}
              value={selectedValue}
              onChange={(value) => {
                const next = (value as ProviderOptionValue) || "bailian-qwen3";
                setSelectedValue(next);
                const opt =
                  providerOptions.find((item) => item.value === next) ||
                  providerOptions[0];
                setProvider(opt.provider);
              }}
            />
            <Group justify="flex-end">
              <Button type="submit">开始</Button>
            </Group>
          </Stack>
        </form>
      </Card>

      {error && (
        <Alert icon={<IconAlertCircle size={16} />} color="red" mt="md">
          {error}
        </Alert>
      )}

      {jobId && (
        <Card withBorder shadow="xs" mt="md" padding="lg" radius="md">
          <Stack gap="sm">
            <Group justify="space-between">
              <div>
                <Text size="sm" c="dimmed">
                  任务 ID
                </Text>
                <Text fw={600}>{jobId}</Text>
                <Text size="sm" c="dimmed">
                  提供方：{selectedOption.label}
                  （转录后统一用 DeepSeek 整理）
                </Text>
              </div>
              <Group gap="xs" align="flex-start">
                <Button
                  size="xs"
                  variant="light"
                  onClick={handleRegenerate}
                  disabled={isProcessing}
                >
                  重新用 DeepSeek 整理
                </Button>
                {stages.map((s) => (
                  <Badge
                    key={s.key}
                    color={stage === s.key ? "blue" : "gray"}
                    variant={stage === s.key ? "filled" : "light"}
                  >
                    {s.label}
                  </Badge>
                ))}
              </Group>
            </Group>

            <Group gap="md">
              <Text>当前阶段：{stageMap[stage as JobStage] || stage}</Text>
              <Text c="dimmed">已处理字数：{wordCount}</Text>
            </Group>

            <Grid gutter="md">
              <Grid.Col span={{ base: 12, sm: 6 }}>
                <Card padding="md" radius="sm" withBorder>
                  <Group gap={6} mb="xs">
                    <Title order={5}>原始转录</Title>
                    {stage === "transcribing" && <Loader size="sm" />}
                  </Group>
                  <Text
                    size="sm"
                    style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}
                  >
                    {raw || "（等待转录中...）"}
                  </Text>
                </Card>
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                <Card padding="md" radius="sm" withBorder>
                  <Group gap={6} mb="xs">
                    <Title order={5}>整理后文本</Title>
                    {stage === "formatting" && <Loader size="sm" />}
                  </Group>
                  <Text
                    size="sm"
                    style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}
                  >
                    {formatted || "（等待整理中...）"}
                  </Text>
                </Card>
              </Grid.Col>
            </Grid>
          </Stack>
        </Card>
      )}
    </Container>
  );
}
