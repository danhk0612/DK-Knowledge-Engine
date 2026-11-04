import { health, searchHelp, askHelp, eventHelp } from "./api-client.js";

const get = (id) => document.getElementById(id);
const result = get("result");
const sources = get("sources");

function product() {
  return [get("product").value.trim(), get("version").value.trim()];
}

function sourceText(items) {
  return items.map((item) => {
    const path = item.source_path ?? "";
    const page = item.page_from == null ? "" : " (p." + item.page_from + ")";
    return path + page;
  }).join("\n");
}

async function perform(action, format) {
  result.textContent = "요청 중…";
  sources.textContent = "";
  try {
    const data = await action();
    const [message, refs] = format(data);
    result.textContent = message;
    sources.textContent = refs ? "출처:\n" + refs : "";
  } catch (error) {
    result.textContent = "요청 실패: " + error.message;
  }
}

get("health").addEventListener("click", () => perform(
  () => health(),
  (data) => ["엔진: " + data.status + " / LLM: " + (data.llm_ready ? "사용 가능" : "미설정"), ""],
));

get("search").addEventListener("click", () => perform(
  () => searchHelp(...product(), get("question").value.trim()),
  (data) => [
    data.results.length
      ? data.results.map((item) => item.title + "\n" + item.excerpt).join("\n\n")
      : "일치하는 문서가 없습니다.",
    sourceText(data.results),
  ],
));

get("chat").addEventListener("click", () => perform(
  () => askHelp(...product(), get("question").value.trim()),
  (data) => [data.answer, sourceText(data.sources)],
));

get("event-help").addEventListener("click", () => perform(
  () => eventHelp(...product(), get("event").value.trim(), get("code").value.trim(), get("screen").value.trim()),
  (data) => [
    data.matched ? data.title + "\n" + data.content :
      data.reason === "ambiguous_rules" ? "중복 규칙이 있어 자동 안내할 수 없습니다." : "해당 오류 도움말이 없습니다.",
    data.matched && data.source ? sourceText([data.source]) : "",
  ],
));
