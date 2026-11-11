# crewai-autom

[CrewAI](https://www.crewai.com) tool for [Autom](https://www.autom.dev), a SERP API that returns live search engine results as JSON.

`AutomSearchTool` lets an agent search the web with Google (the default), Google News, Bing, Brave, DuckDuckGo or Yahoo.

## Installation

```bash
pip install crewai-autom
```

Get an API key at [app.autom.dev](https://app.autom.dev) and set it in the environment:

```bash
export AUTOM_API_KEY="your-api-key"
```

## Usage

```python
from crewai import Agent, Crew, Task
from crewai_autom import AutomSearchTool

search = AutomSearchTool(n_results=5)

researcher = Agent(
    role="Researcher",
    goal="Find current facts on the web",
    backstory="You check recent sources before answering.",
    tools=[search],
)
task = Task(
    description="What changed in the latest Python release?", expected_output="A short summary", agent=researcher
)
Crew(agents=[researcher], tasks=[task]).kickoff()
```

The tool returns a JSON list of results. Each result has `title`, `link`, `snippet` and `position`; news results also have `date` and `source`.

| Option | Default | Description |
| --- | --- | --- |
| `engine` | `google` | `google`, `bing`, `brave`, `duckduckgo` or `yahoo` |
| `search_type` | `search` | `news` searches Google News |
| `n_results` | `5` | Results returned, 1 to 10 |
| `country` | | Two-letter country code, such as `us` (Google only) |
| `language` | | Language code, such as `en` (Google only) |
| `location` | | City or region to search from (Google web search only) |
| `api_key` | `AUTOM_API_KEY` | Autom API key |
| `timeout` | `60` | Seconds to wait for Autom |

API errors are returned to the agent as text, and the key never appears in them. Autom reports a rate limit as HTTP 401 with "Rate limit exceeded"; the tool says "rate limit exceeded" in that case.

## Development

```bash
pip install -e ".[test]"
pytest
```

## License

MIT
