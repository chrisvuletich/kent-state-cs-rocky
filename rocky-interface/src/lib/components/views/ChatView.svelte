<script>
    import "$lib/styles/routes/views/chat.css";

    let input = "";
    let messages = [];
    let chatContainer;

    function showIntroduction(){

        messages = [
            {
                role:"user",
                content:"Introduce yourself."
            },
            {
                role:"assistant",
                content: `Hello! I'm Rocky AI, Kent State University's AI assistant.

        I can help answer questions, explain concepts, assist with coursework, and provide information about Rocky and Kent State resources.
        Please remember that conversations may be logged and reviewed, and you should avoid sharing sensitive information.`
                }
            ];
            setTimeout(scrollToBottom, 0);
    }

    function showCapabilities(){

        messages = [
            {
                role:"user",
                content:"What are your capabilities?"
            },
            {
                role:"assistant",
                content: `Rocky AI can:

    • Explain computer science concepts
    • Help understand assignments
    • Answer questions about Rocky
    • Provide general assistance
    • Help brainstorm ideas and projects`
            }
        ];
        setTimeout(scrollToBottom, 0);
    }

    function showPrivacy(){

        messages = [
            {
                role:"user",
                content:"What should I avoid sharing?"
            },
            {
                role:"assistant",
                content: `Privacy & Safety

    • Conversations may be logged and reviewed.
    • Do not share passwords or sensitive information.
    • Rocky AI may occasionally make mistakes.
    • Verify important academic or administrative information with official university resources.`
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
                    message: userMessage
                })
            });

            const data = await response.json();
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
        {msg.content}
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
