import type { TaskStatus } from '../types'

export type Locale = 'zh-TW' | 'zh-CN' | 'en-US'

const statusMessages: Record<Locale, Record<TaskStatus, string>> = {
  'zh-TW': { pending: '待執行', processing: '執行中', need_review: '等待審核', approved: '已核准', rejected: '已退回', failed: '失敗' },
  'zh-CN': { pending: '待执行', processing: '执行中', need_review: '等待审核', approved: '已批准', rejected: '已退回', failed: '失败' },
  'en-US': { pending: 'Pending', processing: 'Running', need_review: 'Awaiting review', approved: 'Approved', rejected: 'Returned', failed: 'Failed' },
}

export function statusText(locale: Locale, status: TaskStatus): string {
  return statusMessages[locale][status]
}

export function formatDateTime(locale: Locale, value: string): string {
  return new Date(value).toLocaleString(locale, { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false })
}

export function formatNumber(locale: Locale, value: number): string {
  return new Intl.NumberFormat(locale).format(value)
}

