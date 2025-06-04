import json
from datetime import datetime, timezone
from typing import TypedDict, Annotated

from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, BaseMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from dotenv import load_dotenv
load_dotenv()

# Инструмент
class GetCurrentTimeInput(BaseModel):
    pass

@tool(args_schema=GetCurrentTimeInput)
def get_current_time():
    """Returns the current UTC time in ISO-8601 format."""
    return {"utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}

# Состояние
class State(TypedDict):
    messages: Annotated[list, "A list of chat messages"]

# Модель и биндинг инструментов
llm = ChatOpenAI(model="gpt-4o", temperature=0.7)
llm_with_tools = llm.bind_tools([get_current_time])

def chat_node(state):
    messages = state["messages"]
    if not messages:  # Проверка на пустой список
        return {"messages": messages}

    # Логирование для отладки
    print("Input messages:", messages)

    # Преобразование JSON-сообщений из Studio в HumanMessage
    processed_messages = []
    for msg in messages:
        if isinstance(msg, dict) and "role" in msg and "content" in msg:
            if msg["role"] == "user":
                processed_messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                processed_messages.append(AIMessage(content=msg["content"]))
            else:
                processed_messages.append(msg)
        else:
            processed_messages.append(msg)

    messages = processed_messages
    print("Processed messages:", messages)

    if not messages:  # Дополнительная проверка после преобразования
        return {"messages": messages}

    last_message = messages[-1]  # Теперь безопасно, так как messages не пуст
    response = llm_with_tools.invoke(messages)
    messages.append(response)

    return {"messages": messages}
    return {"messages": messages}
# Состояние обработки запроса, проверка на вызов инструмента
def process_node(state):
    messages = state["messages"]
    if not messages:  # Проверка на пустой список
        return {"messages": messages}

    last_message = messages[-1] if messages else None
    if not last_message or not isinstance(last_message, AIMessage):
        return {"messages": messages}

    # Вызов инструмента
    if "tool_calls" in last_message.additional_kwargs:
        tool_calls = last_message.additional_kwargs.get("tool_calls", [])
        for tool_call in tool_calls:
            if tool_call["function"]["name"] == "get_current_time":
                result = get_current_time.invoke({})
                messages.append(
                    ToolMessage(
                        tool_call_id=tool_call["id"],
                        content=json.dumps(result)
                    )
                )
        # Повторный вызов GPT с результатом
        if tool_calls:  # Вызываем только если были tool_calls
            final_response = llm_with_tools.invoke(messages)
            messages.append(final_response)

    return {"messages": messages}

# Создание и компиляция графа
builder = StateGraph(State)
builder.add_node("chat", chat_node)
builder.add_node("process", process_node)
builder.set_entry_point("chat")
builder.add_edge("chat", "process")
builder.add_edge("process", END)
app = builder.compile()

# Точка входа
def main():
    print("🤖 LangGraph Stateless ChatBot (type 'exit' to quit)")
    while True:
        user_input = input("You: ")
        if user_input.lower() in {"exit", "quit"}:
            print("Bye!")
            break
        state = {"messages": [HumanMessage(content=user_input)]}
        result = app.invoke(state)
        print("Bot:", result["messages"][-1].content)

if __name__ == "__main__":
    main()

