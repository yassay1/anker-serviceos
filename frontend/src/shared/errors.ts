export function readableError(error: unknown) {
  return error instanceof Error ? error.message : '服务暂时不可用，请稍后重试。'
}
