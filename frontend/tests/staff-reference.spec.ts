import { test, expect } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { fixture, ids } from './workspace-fixture'
import type { components } from '../src/api/schema'

test('staff references: four workspaces preserve navigation, replies and record access', async ({ page }) => {
  const state = await fixture(page)
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  const record: components['schemas']['CaseRead'] = { id: ids.second, customer_id: ids.customer,
    problem_text: '充电接口不稳定', user_goal: '恢复稳定充电', status: 'WAITING_CUSTOMER', version: 2, created_at: '2026-10-14T01:00:00Z' }
  await page.route('**/api/v1/cases**', route => {
    const path = new URL(route.request().url()).pathname
    const json = path.endsWith('/cases') ? [record] : path.endsWith(`/cases/${ids.second}`) ? record
      : path.endsWith('/evidence') ? { items: [], next_cursor: null } : []
    return route.fulfill({ json })
  })
  await page.route('**/fact-review', route => route.fulfill({ json: [] }))
  mkdirSync('../.runtime/staff-ui', { recursive: true })
  await page.goto('/desk?view=overview')
  await expect(page.getByRole('heading', { name: '服务处理队列' })).toBeVisible()
  expect(await page.locator('.service-content').evaluate(element => getComputedStyle(element).backgroundColor)).toBe('rgb(255, 248, 237)')
  await expect(page.locator('.queue-table tbody tr')).toHaveCount(1)
  await page.screenshot({ path: '../.runtime/staff-ui/overview.png', fullPage: true })

  await page.locator('.staff-navigation').getByRole('link', { name: '服务会话', exact: true }).click()
  await expect(page.locator('.staff-conversation-item')).toHaveCount(2)
  await expect(page.locator('.staff-conversation-context')).toBeVisible()
  const columns = await page.locator('.chat-layout').evaluate(element => getComputedStyle(element).gridTemplateColumns.split(' ').map(Number.parseFloat))
  expect(columns).toHaveLength(3)
  expect(columns[1]).toBeGreaterThan(columns[0])
  expect(columns[1]).toBeGreaterThan(columns[2])
  const listBox = await page.locator('.conversation-list').boundingBox()
  const chatBox = await page.locator('.chat-panel').boundingBox()
  expect(Math.abs(listBox!.height - chatBox!.height)).toBeLessThan(2)
  await expect(page.getByRole('button', { name: '批准', exact: true })).toBeVisible()
  expect(await page.locator('.message p').first().evaluate(element => getComputedStyle(element).fontSize)).toBe('16px')
  expect(await page.locator('.composer textarea').evaluate(element => getComputedStyle(element).fontSize)).toBe('16px')
  await expect(page.locator('.staff-conversation-item').first()).toContainText('收到，我们在这段会话继续处理')
  await expect(page.locator('.staff-conversation-item').nth(1)).toContainText('建于')
  await expect(page.getByRole('checkbox')).toHaveCount(0)
  await page.getByRole('textbox', { name: '回复客户', exact: true }).fill('已收到补充信息，我们在当前会话继续核对。')
  await page.getByRole('button', { name: '发送回复', exact: true }).click()
  await expect.poll(() => state.sent.length).toBe(1)
  expect(state.sent[0].visibility).toBe('PUBLIC')
  await page.getByRole('button', { name: '内部备注', exact: true }).click()
  await page.getByRole('textbox', { name: '回复客户', exact: true }).fill('客服内部核对记录。')
  await page.getByRole('button', { name: '保存内部备注', exact: true }).click()
  await expect.poll(() => state.sent.length).toBe(2)
  expect(state.sent[1].visibility).toBe('INTERNAL')
  await page.getByRole('button', { name: '回复客户', exact: true }).click()
  await page.getByRole('button', { name: '上传图片', exact: true }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.getByRole('button', { name: '关闭图片上传' }).click()
  await page.locator('.staff-conversation-item').nth(1).click()
  await expect(page.getByRole('textbox', { name: '回复客户', exact: true })).toBeDisabled()
  await page.locator('.staff-conversation-item').first().click()
  await expect(page.getByRole('textbox', { name: '回复客户', exact: true })).toBeEnabled()
  await page.getByRole('button', { name: '请求补充图片', exact: true }).click()
  await expect(page.getByRole('textbox', { name: '回复客户', exact: true })).toHaveValue(/为了进一步核对问题/)
  expect(state.sent).toHaveLength(2)
  await page.getByRole('button', { name: '人工协作与审批', exact: true }).click()
  await expect(page.getByRole('button', { name: '批准', exact: true })).toBeEnabled()
  await page.locator('#staff-collaboration .collaboration-settings > summary').click()
  await page.getByRole('textbox', { name: '回复客户', exact: true }).clear()
  await page.locator('.staff-conversation-context').evaluate(element => { element.scrollTop = 0 })
  await page.screenshot({ path: '../.runtime/staff-ui/conversation.png', fullPage: true })

  await page.locator('.staff-navigation').getByRole('link', { name: '服务案例', exact: true }).click()
  await expect(page.locator('.staff-case-table tbody tr')).toHaveCount(1)
  await page.getByRole('button', { name: /充电接口不稳定/ }).click()
  await expect(page.locator('.case-preview-title')).toHaveText(record.problem_text)
  await page.screenshot({ path: '../.runtime/staff-ui/cases.png', fullPage: true })
  await page.getByRole('link', { name: '查看详情', exact: true }).click()
  await expect(page.getByRole('heading', { name: '模拟售后动作', exact: true })).toBeVisible()

  await page.locator('.staff-navigation').getByRole('link', { name: '设备管理', exact: true }).click()
  await expect(page.locator('.staff-device-hero h2')).toHaveText('Anker 737')
  await page.locator('.staff-device-list li a').first().click()
  await expect(page.locator('.staff-device-list a.selected')).toBeVisible()
  await page.screenshot({ path: '../.runtime/staff-ui/devices.png', fullPage: true })
  await page.getByRole('button', { name: '已核验事实', exact: true }).first().click()
  await expect(page.getByText('充电功率（瓦）', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '关联服务历史', exact: true }).click()
  await expect(page.locator('.staff-device-main').getByRole('link', { name: record.problem_text })).toBeVisible()
  await page.setViewportSize({ width: 1366, height: 900 })
  await page.goto(`/desk?conversation=${ids.conversation}`)
  await expect(page.locator('.staff-conversation-context')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('button', { name: '资料', exact: true }).click()
  await expect(page.locator('.staff-conversation-context')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  expect(errors).toEqual([])
})

for (const count of [0, 1, 2]) {
  test(`case conversation navigation resolves ${count} actual associations`, async ({ page }) => {
    await fixture(page)
    const record: components['schemas']['CaseRead'] = { id: ids.second, customer_id: ids.customer,
      problem_text: '充电接口不稳定', user_goal: '恢复稳定充电', status: 'WAITING_CUSTOMER', version: 2, created_at: '2026-10-14T01:00:00Z' }
    await page.route('**/api/v1/cases', route => route.fulfill({ json: [record] }))
    await page.route('**/case-summaries', route => route.fulfill({ json:
      count === 2 || count === 1 && route.request().url().includes(ids.conversation)
        ? [{ case: record, device_ids: [], facts: [] }] : [] }))
    await page.goto('/cases')
    await page.getByRole('button', { name: '进入服务会话', exact: true }).click()
    if (count === 1) await expect(page).toHaveURL(new RegExp(`conversation=${ids.conversation}`))
    else {
      const options = page.getByRole('region', { name: '选择关联服务会话' })
      if (count === 0) {
        await expect(options).toContainText('没有此案例的关联记录')
        await expect(page).toHaveURL(/\/cases$/)
      } else {
        await expect(options.getByRole('link')).toHaveCount(2)
        await page.setViewportSize({ width: 390, height: 844 })
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
        await expect(page).toHaveURL(/\/cases$/)
        await options.getByRole('link').nth(1).click()
        await expect(page).toHaveURL(new RegExp(`conversation=${ids.second}`))
      }
    }
  })
}
