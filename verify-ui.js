// ViewDL 极简改版 · 无头验证：结构断言 + 真实解析交互 + 截图
const path = "C:/Users/weizhiyu/.trae-cn/binaries/node/versions/24.15.0/node_modules/@playwright/cli/node_modules/playwright";
const { chromium } = require(path);

const BASE = "http://127.0.0.1:8770";
const KOU = "4.35 复制打开抖音，看看【神仙小分队的作品】反正就是随地大小跳 https://v.douyin.com/hPzeqGEmUZQ/";

(async () => {
  const browser = await chromium.launch({ args: ["--no-proxy-server"] });
  const page = await browser.newPage({ viewport: { width: 720, height: 900 } });
  const shots = "H:/新建文件夹/设计文件/樊清正/个人/rea/viewdl/_shots";
  const fs = require("fs"); fs.mkdirSync(shots, { recursive: true });

  page.on("pageerror", e => console.log("PAGEERROR:", e.message));
  page.on("console", m => { if (m.type() === "error") console.log("CONSOLE-ERR:", m.text().slice(0, 200)); });
  await page.goto(BASE, { waitUntil: "networkidle" });
  console.log("typeof parse:", await page.evaluate(() => typeof parse),
              "| fetch probe:", await page.evaluate(() =>
                fetch("/api/jobs").then(r => r.status).catch(e => "FETCH-FAIL: " + e.message)));

  // —— 结构断言：砍掉的东西确实没了，留下的都在 ——
  const asserts = [];
  const expect = (name, cond) => asserts.push([name, !!cond]);
  expect("无 hero 标语 h1", await page.locator("h1").count() === 0);
  expect("无平台 chips", await page.locator(".chip").count() === 0);
  expect("无使用说明卡片", await page.locator(".f-item").count() === 0);
  expect("无 note 提示框", await page.locator("#noteBox").count() === 0);
  expect("wordmark 存在", (await page.locator(".wordmark").textContent()) === "ViewDL");
  expect("textarea aria-label", (await page.locator("#input").getAttribute("aria-label")) === "链接");
  expect("结果区默认隐藏", await page.locator("#result").isHidden());
  // 区块可见性与数据一致性（等首个 1.2s 刷新 tick 后判定）
  await page.waitForTimeout(1600);
  const jobsN = (await (await page.request.get(BASE + "/api/jobs")).json()).jobs.length;
  const recsN = (await (await page.request.get(BASE + "/api/history")).json()).files.length;
  expect("任务区随数据显示", (await page.locator("#tasksSec").isVisible()) === (jobsN > 0));
  expect("记录区随数据显示", (await page.locator("#recSec").isVisible()) === (recsN > 0));
  console.log("数据一致性: jobs", jobsN, "records", recsN);
  const bad2 = asserts.filter(x => !x[1]);
  console.log(bad2.length ? "存在失败断言: " + JSON.stringify(bad2) : "结构断言全部通过 " + asserts.length + " 项");
  await page.screenshot({ path: shots + "/1-empty.png", fullPage: true });

  // —— 真实解析交互（B站，快且稳） ——
  await page.fill("#input", "BV1GJ411x7h7 https://www.bilibili.com/video/BV1GJ411x7h7");
  await page.click("#go");
  await page.waitForSelector("#result:not([hidden])", { timeout: 45000 })
    .catch(async () => {
      const snap = await page.evaluate(() => ({
        btn: document.querySelector("#go").textContent,
        errHidden: document.querySelector("#err").hidden,
        err: document.querySelector("#err").textContent.slice(0, 120),
        resultHidden: document.querySelector("#result").hidden,
      }));
      console.log("TIMEOUT-快照:", JSON.stringify(snap));
      const t0 = Date.now();
      const st = await page.evaluate(async () => {
        try {
          const r = await fetch("/api/parse", { method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text: "BV1GJ411x7h7 https://www.bilibili.com/video/BV1GJ411x7h7" }) });
          return r.status + " items=" + Object.keys(await r.json()).length;
        } catch (e) { return "PAGE-FETCH-FAIL: " + e.message; }
      });
      console.log("页内直发 POST:", st, "耗时", Date.now() - t0, "ms");
      throw new Error("result 未出现（见上方快照）");
    });
  const meta = await page.locator("#meta").textContent();
  const radios = await page.locator('input[name=q]').count();
  const btnText = await page.locator("#dl").textContent();
  console.log("meta:", meta, "| 清晰度档数:", radios, "| 按钮:", btnText);
  expect("meta 含平台", meta.includes("哔哩哔哩"));
  expect("清晰度 radio 组", radios >= 2);
  expect("按钮带计数", /下载 \d+ 个文件/.test(btnText));
  expect("标题非空", ((await page.locator("#title").textContent()) || "").length > 3);

  // 换档 + 反选交互
  await page.locator('input[name=q]').nth(1).check();
  const btnAfter = await page.locator("#dl").textContent();
  expect("换档后按钮保持计数", /下载 \d+ 个文件/.test(btnAfter));
  await page.screenshot({ path: shots + "/2-result.png", fullPage: true });

  // —— 错误态 ——
  await page.fill("#input", "这不是链接");
  await page.click("#go");
  await page.waitForSelector("#err:not([hidden])", { timeout: 20000 });
  const errText = await page.locator("#err").textContent();
  console.log("错误态:", errText.slice(0, 40), "…");
  expect("错误提示可见", errText.length > 4);
  await page.screenshot({ path: shots + "/3-error.png" });

  // —— 记录区（已有历史文件） ——
  await page.waitForTimeout(400);
  const recVisible = await page.locator("#recSec").isVisible();
  console.log("记录区可见:", recVisible);

  const badEnd = asserts.filter(x => !x[1]);
  console.log(badEnd.length ? "存在失败断言: " + JSON.stringify(badEnd) : "交互断言全部通过 " + asserts.length + " 项");
  await browser.close();
})().catch(e => { console.error("SCRIPT_FAIL:", e.message); process.exit(1); });
