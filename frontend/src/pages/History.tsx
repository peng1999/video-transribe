import { useQuery } from "@tanstack/react-query";
import { listJobs } from "../api";
import { Link } from "react-router-dom";
import {
  Card,
  Container,
  Group,
  Stack,
  Text,
  Title,
  Anchor,
  Badge,
} from "@mantine/core";

export default function History() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["jobs"],
    queryFn: listJobs,
  });

  if (isLoading) return <p>加载中...</p>;
  if (error) return <p>加载失败</p>;

  return (
    <Container size="lg" py="md">
      <Title order={3} mb="md">
        历史记录
      </Title>
      <Stack gap="sm">
        {data?.map((job) => (
          <Card withBorder padding="md" radius="md" key={job.id}>
            <Group justify="space-between" align="flex-start" mb="xs">
              <div>
                <Text fw={600}>{job.url}</Text>
                <Text size="sm" c="dimmed">
                  创建时间：{new Date(job.created_at).toLocaleString()}
                </Text>
              </div>
              <Badge
                color={
                  job.status === "done"
                    ? "green"
                    : job.status === "error"
                    ? "red"
                    : "blue"
                }
              >
                {job.status}
              </Badge>
            </Group>
            {job.formatted_text && (
              <Text size="sm" c="dimmed" mb="xs">
                {job.formatted_text.slice(0, 120)}...
              </Text>
            )}
            <Anchor component={Link} to={`/?job=${job.id}`} size="sm">
              查看
            </Anchor>
          </Card>
        ))}
      </Stack>
    </Container>
  );
}
