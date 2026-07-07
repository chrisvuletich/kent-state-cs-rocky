<script>
    import "$lib/styles/routes/views/chat.css";
    import SvelteMarkdown from "@humanspeak/svelte-markdown";

    let input = "";
    let messages = [];
    let conversationId = "";
    let chatContainer;

    function showIntroduction(){
        conversationId = "";

        messages = [
            {
                role:"user",
                content:"Introduce yourself."
            },
            {
                role:"assistant",
                content: `# 👋 Meet Rocky AI

Welcome! I'm **Rocky AI**, the Kent State Computer Science assistant.

My goal is to help students learn, explore new ideas, and make coursework a little easier. Whether you're learning to program, studying for an exam, or working on a project, I'm here to help explain concepts and answer questions.

I'm designed to be a learning companion—not just a source of answers.

> Ask me anything related to computer science, programming, or Rocky, and we'll work through it together.

## Before you get started

Please keep these things in mind:

- Conversations **may be logged and reviewed** to improve the system.
- **Do not share** passwords, API keys, or other sensitive personal information.
- AI can make mistakes, so **verify important academic or university information** with official Kent State resources.

> **Tip:** Try asking a programming question, requesting an explanation of a concept, or asking for help debugging your code.
`
                }
            ];
            setTimeout(scrollToBottom, 0);
    }

    function showCapabilities(){
        conversationId = "";

        messages = [
            {
                role:"user",
                content:"What are your capabilities?"
            },
            {
                role:"assistant",
                content: `# 🚀 What can Rocky AI do?

Rocky AI is designed to assist **Kent State Computer Science students** with a variety of tasks.

## I can help with

- 💻 Explaining programming concepts
- 🐞 Debugging code and understanding errors
- 📖 Breaking down algorithms and data structures
- 📝 Brainstorming projects and assignments
- 🧠 Answering general computer science questions

## Things to remember

- I can explain concepts, but I won't always have the correct answer.
- I work best when you provide **clear questions** and **relevant context**.
- If you're asking about code, include the code snippet or error message whenever possible.

> **Tip:** Instead of asking *"It doesn't work,"* try describing what you expected to happen and what actually happened.
`
            }
        ];
        setTimeout(scrollToBottom, 0);
    }

    function showPrivacy(){
        conversationId = "";

        messages = [
            {
                role:"user",
                content:"What should I avoid sharing?"
            },
            {
                role:"assistant",
                content: `# 🔒 Privacy & Safety

Before you start chatting, here are a few things to keep in mind.

## Protect your information

For your security, **don't share**:

- 🔑 Passwords or API keys
- 💳 Credit card or banking information
- 🪪 Social Security numbers or other sensitive personal information
- 📄 Confidential university or work documents

## Using Rocky AI responsibly

- Conversations **may be logged and reviewed** to help improve Rocky AI.
- AI responses may occasionally be inaccurate or incomplete.
- Always verify important academic, administrative, or university information with official Kent State resources.

## A good rule of thumb

If you wouldn't post it publicly or email it to a stranger, don't share it with an AI assistant.

> **Your privacy matters.** When in doubt, leave personal or sensitive information out of your conversation.
`
            }
        ];
        setTimeout(scrollToBottom, 0);
    }

    function scrollToBottom() {
        if (chatContainer) {
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }
    }

    async function sendMessage(){
        const userMessage = input.trim();

        if(userMessage === ""){
            return;
        }

        messages = [
            ...messages,
            {
                role: "user",
                content: userMessage
            }
        ];
        input = "";

        setTimeout(scrollToBottom, 0);

        try{
            const response = await fetch("/api/chat", {
                method:"POST",
                headers:{
                    "Content-Type":"application/json"
                },
                body: JSON.stringify({
                    message: userMessage,
                    ...(conversationId ? { conversation_id: conversationId } : {})
                })
            });

            const data = await response.json();

            if (response.ok && typeof data?.conversation_id === "string") {
                conversationId = data.conversation_id;
            }

            const reply = response.ok && typeof data?.reply === "string" && data.reply.trim() !== ""
                ? data.reply
                : (typeof data?.error === "string" && data.error.trim() !== ""
                    ? data.error
                    : "Rocky AI did not return a reply.");

            messages = [
                ...messages,
                {
                    role: "assistant",
                    content: reply
                }
            ];
        }
        catch(error){
            console.error(error);

        messages = [
            ...messages,
            {
                role: "assistant",
                content: "Unable to contact Rocky AI at this time."
            }
        ];

        }
        setTimeout(scrollToBottom, 0);
    }
</script>

<div class="chat-header">
    <h1 class="chat-title">Rocky AI</h1>
    <p class="chat-subtitle">Kent State Computer Science Assistant</p>
</div>

<div class="chat" bind:this={chatContainer}>
    {#if messages.length === 0}
    <div class="welcome">
        <h2>Welcome to Rocky AI</h2>
        <p>
            Ask questions about courses, assignments,
            computer science topics, or anything.
        </p>

        <div class="disclaimer">
        Rocky AI conversations may be logged and reviewed to improve the system and ensure appropriate use. Do not share sensitive personal information.
        </div>

        <div class="examples">
            <button onclick={() => {showIntroduction();}}>
                Introduce Rocky
            </button>

            <button onclick={() => {showCapabilities();}}>
                Capabilities
            </button>

            <button onclick={() => {showPrivacy();}}>
                Privacy & Safety
            </button>
        </div>
    </div>
    {/if}

    {#each messages as msg}
        <div class="message {msg.role}">
            {#if msg.role === "assistant"}
                <SvelteMarkdown source={msg.content} />
            {:else}
                {msg.content}
            {/if}
        </div>
    {/each}
</div>

<div class="bottom">

  <input
  class="messageInput"
  bind:value={input}
  placeholder="Type a message..."
  onkeydown={(e)=>{
    if(e.key === "Enter"){
        sendMessage()
    }
  }}
  />

  <button class="sendButton" onclick={sendMessage}>↑</button>
</div>
