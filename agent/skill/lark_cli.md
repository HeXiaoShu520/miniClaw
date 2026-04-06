# lark-cli 技能使用教程

lark-cli 是飞书官方命令行工具，支持通过用户身份（OAuth）操作飞书的消息、日历、任务、文档等功能。

## 安装

```bash
npm install -g @larksuiteoapi/lark-cli
```

## 授权登录

首次使用需要完成 OAuth 授权：

```bash
# 开通所有常用权限（多维表格、日历、通讯录、文档、消息、邮箱、表格、任务、视频会议）
lark-cli auth login --domain base,calendar,contact,docs,im,mail,sheets,task,vc --recommend
```

执行后会输出一个验证链接，在浏览器中打开并完成授权即可。

```bash
# 查看授权状态
lark-cli auth status
```

---

## 消息（IM）

```bash
# 发送文本消息给用户
lark-cli im +messages-send --user-id ou_xxxxxx --text "你好！"

# 发送消息到群聊
lark-cli im +messages-send --chat-id oc_xxxxxx --text "群公告内容"
```

> 注意：`im +messages-send` 不支持 `--format` 参数，去掉即可。

---

## 日历（Calendar）

```bash
# 查看今天日程
lark-cli calendar +agenda

# 查看指定日期日程（用 --start/--end，不支持 --date）
lark-cli calendar +agenda --start "2026-04-07T00:00:00+08:00" --end "2026-04-07T23:59:59+08:00"

# 创建日程
lark-cli calendar +create \
  --summary "团队周会" \
  --start "2026-04-07T14:00:00+08:00" \
  --end "2026-04-07T15:00:00+08:00" \
  --description "讨论本周进展" \
  --attendees "ou_aaa,ou_bbb"

# 查询用户空闲时间（用 --start/--end，不支持 --date）
lark-cli calendar +freebusy --user-id ou_xxxxxx \
  --start "2026-04-07T00:00:00+08:00" \
  --end "2026-04-07T23:59:59+08:00"
```

---

## 任务（Task）

```bash
# 创建任务（用 --summary，不支持 --title）
lark-cli task +create \
  --summary "完成需求文档" \
  --due "2026-04-08T18:00:00+08:00" \
  --description "包含功能说明和接口设计"

# 完成任务
lark-cli task +complete --task-id <task_guid>
```

> 注意：`task +get-my-tasks` 只返回在任务清单中的任务，直接创建的任务需用 `task tasks get --params '{"task_guid":"..."}'` 查询。

---

## 文档（Docs）

```bash
# 创建文档（保存到个人文库）
lark-cli docs +create \
  --title "文档标题" \
  --wiki-space my_library \
  --markdown "# 正文内容"

# 获取文档内容（用 --doc，不支持 --url）
lark-cli docs +fetch --doc "https://xxx.feishu.cn/docx/xxxxxx"

# 更新文档（追加模式）
lark-cli docs +update --doc "https://xxx.feishu.cn/docx/xxxxxx" --mode append --markdown "# 新内容"

# 更新文档（替换指定文字，需配合 --selection-with-ellipsis）
lark-cli docs +update --doc "https://xxx.feishu.cn/docx/xxxxxx" \
  --mode replace_all \
  --selection-with-ellipsis "要替换的文字" \
  --markdown "新内容"

# 搜索文档
lark-cli docs +search --query "关键词"
```

---

## 表格（Sheets）

```bash
# 获取表格信息（含 sheet-id）
lark-cli sheets +info --url "https://xxx.feishu.cn/sheets/xxxxxx"

# 读取表格数据（需要 --sheet-id，不能只用 --url）
lark-cli sheets +read \
  --url "https://xxx.feishu.cn/sheets/xxxxxx" \
  --sheet-id "846c5a" \
  --range "A1:D10"

# 写入表格数据（覆盖）
lark-cli sheets +write \
  --url "https://xxx.feishu.cn/sheets/xxxxxx" \
  --sheet-id "846c5a" \
  --range "A1:D1" \
  --values '[["列1","列2","列3","列4"]]'

# 追加表格数据（range 行数需 >= values 行数）
lark-cli sheets +append \
  --url "https://xxx.feishu.cn/sheets/xxxxxx" \
  --sheet-id "846c5a" \
  --range "A1:D3" \
  --values '[["行1列1","行1列2"],["行2列1","行2列2"]]'
```

> 注意：`sheets` 系列命令均不支持 `--format` 参数。

---

## 云盘（Drive）

```bash
# 上传文件（必须使用相对路径，先 cd 到文件所在目录）
cd /path/to/dir
lark-cli drive +upload --file ./myfile.txt --name "上传后的文件名.txt"

# 下载文件
lark-cli drive +download \
  --file-token "ZdZrbCMKzoOUPlxbMPccawsNn4c" \
  --output ./downloaded.txt \
  --overwrite

# 给文档添加评论（支持 wiki URL，--content 必须是 JSON 数组）
lark-cli drive +add-comment \
  --doc "https://xxx.feishu.cn/wiki/xxxxxx" \
  --content '[{"type":"text","text":"评论内容"}]' \
  --full-comment
```

---

## 知识库（Wiki）

```bash
# 列出知识库空间
lark-cli wiki spaces list

# 列出知识库节点
lark-cli wiki nodes list --params '{"space_id":"7613842045064449226"}'
```

---

## 多维表格（Base）

```bash
# 创建多维表格
lark-cli base +base-create --name "我的多维表格" --time-zone "Asia/Shanghai"

# 查看数据表列表
lark-cli base +table-list --base-token "OAPAb5GDqaP6oMsd0vCco4hmnxg"

# 查看字段列表
lark-cli base +field-list \
  --base-token "OAPAb5GDqaP6oMsd0vCco4hmnxg" \
  --table-id "tbl0hloZoDt8Wgyf"

# 写入记录（--json 直接传字段对象，不需要套 {"fields": ...}）
lark-cli base +record-upsert \
  --base-token "OAPAb5GDqaP6oMsd0vCco4hmnxg" \
  --table-id "tbl0hloZoDt8Wgyf" \
  --json '{"文本":"内容"}'

# 读取记录
lark-cli base +record-list \
  --base-token "OAPAb5GDqaP6oMsd0vCco4hmnxg" \
  --table-id "tbl0hloZoDt8Wgyf"
```

---

## 联系人（Contact）

```bash
# 获取自己的用户信息
lark-cli contact +get-user

# 获取指定用户信息
lark-cli contact +get-user --user-id ou_xxxxxx

# 搜索用户
lark-cli contact +search-user --query "姓名关键词"
```

---

## 视频会议（VC）

```bash
# 搜索会议记录
lark-cli vc +search --start "2026-03-01" --end "2026-04-06"
```

---

## 在飞书机器人中使用（lark_cli skill）

miniClaw 机器人已集成 lark-cli 作为 Agent 技能，支持的 action：

| action | 说明 | 必填参数 |
|--------|------|----------|
| send_message | 发消息给用户 | user_id, text |
| get_agenda | 查看日程 | date（可选） |
| create_event | 创建日程 | summary, start, end |
| create_task | 创建任务 | summary |
| query_freebusy | 查询空闲时间 | user_id |
| search_user | 搜索/获取用户 | query 或 user_id |
| sheets_read | 读取表格 | spreadsheet_url, sheet_id, range |
| sheets_write | 写入表格 | spreadsheet_url, sheet_id, range, values |
| sheets_append | 追加表格 | spreadsheet_url, sheet_id, range, values |
| drive_upload | 上传文件 | file_path |
| drive_download | 下载文件 | file_token, output_path |
| drive_add_comment | 给文档添加评论 | doc, comment |
| wiki_list_spaces | 列出知识库空间 | 无 |
| wiki_list_nodes | 列出知识库节点 | space_id |
| base_create | 创建多维表格 | base_name |
| base_read | 读取多维表格记录 | base_token, table_id |
| base_write | 写入多维表格记录 | base_token, table_id, record |

自然语言示例：
- "帮我明天下午2点创建一个团队会议日程"
- "给张三发一条消息：明天记得开会"
- "帮我创建一个任务：完成需求文档，截止明天"
- "查看我今天的日程"
- "把这个文件上传到云盘"
- "读取表格 A1:D10 的数据"

> 注意：lark-cli 使用的是你的用户身份（OAuth），所有操作都以你的名义执行，请谨慎使用。
