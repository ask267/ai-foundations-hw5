# AI Prompt Log — Homework 5

Use this file to record the prompts used for each homework problem. Replace the bracketed placeholders with the exact problem information and prompts.

## Section 2 — Problem 2: Study the Campus Customs Database

### Prompt 1

okay now for problem 2. open data/campus_customs.db and look through every table and its fields. copy the original file to data/campus_customs_new.db later probelms will update that working copy. study the three open ticket so u see how they link to the other tables. 
in output/harness.md for each table list the fields and one short line on why that table matters for the agents.

### What I was lacking after the first prompt

[What was missing or wrong after the first prompt, or "Nothing was lacking"]

### Prompt 2

[Paste the follow-up prompt here, or "n/a"]

## Section 3 — Problem 3: Build the MCP server

### Prompt 1

okay now for problem 3. write an mcp server in mcp-server/ using FastMCP. it will talk to data/campus_customs_new.db. do not need to connect or run it in this problem. every agent in this homework will use the tools in this mcp server for now write three tools you know you will need for the tickets in the database keep the names clear and do not invent any data only use the information in this database. 
then in output/harness.md list each of the three MCP tools and for each tool include the following: which table it reads, which ticket it helps unlock 101 102 or 103, and one sentence on why that tool is the right one for that ticket. vague lines like "reads inventory" scores low, tie the tool to the ticket. also add a short mcp_server/README.md file that explains what the mcp server is for, which database file it uses, and the three tools it has

### What I was lacking after the first prompt

[What was missing or wrong after the first prompt, or "Nothing was lacking"]

### Prompt 2

[Paste the follow-up prompt here, or "n/a"]

## Section 4 — Problem 4: Add the MCP server to vibe coder and test each tool

### Prompt 1

okay now for problem 4. in claude code, add your mcp server to this project so the vibe coder can call the tools. save the connection json text in .mcp.json at the project root or however you save local mcp server lists. then test each of the three mcp tools and save the evidence in output/mcp_smoke.json. for every tool include the prompt you asked the vibe coder, the tool name, and the tool output (which must match values in data/campus_customs_new.db)

### What I was lacking after the first prompt

I wanted to double check the the tool output values matched the database values accurately. 

### Prompt 2

does the tool output match the values in data/campus_customs_new.db

## Section 5 — Problem 5: Build the agent team and grow the MCP tools

### Prompt 1

okay now for problem 5. this has a lot of info and steps so work carefully. 
build the agentic team for campus customs using PydanticAI: Boss, Inventory, Accounting, Facilities, and Customer Service. include prompts, models and agent loops so they can delegate work to each other with full connectivity. put the agent prompts in backend/prompts/ with one file per agent. put data types in backend/models.py. and the agent files under backend/ your layout can vary as long as the five roles are clear. Use PORTKEY_API_KEY and only gpt-6-luna for every agent. write each pormpt in your own words with the shop rules the agent needs. more detailed prompts that cover all aspects of an agent's work and scope score higher than a short generic prompt. 
Add any tools the agents need to your MCP server so they can work on the open tickets. shop facts come from the MCP server over data/campus_customs.db. DO NOT invent a second shop-tools layer that bypasses MCP. also wire the agents so they append to output.audit_trail.json as they run - for each agent-loop step, record enough to audit later and append to this file do not wipe it each run. 
In output/harness.md  list each agent and each MCP tool including the ones you add in this problem along with which table the tool uses. also add a short safety section witht the guardrails a real business would want when agents touch reach customers and real money plus limits that keep token use in check. finally, update the mcp_server/README.md so that the tool list matches what you have now.

### What I was lacking after the first prompt

[What was missing or wrong after the first prompt, or "Nothing was lacking"]

### Prompt 2

[Paste the follow-up prompt here, or "n/a"]

## Section 6 — Problem 6: Plan the three tickets

### Prompt 1

okay now for problem 6. before you wire the backend, write down what you expect the team to do on each open ticket. build the output/desk_tickets.html which is a page you can double click with one tab per ticket 101, 102, 103. also add empty Cash and Reflection tabs for later problems leave them blank for now. on each ticket tab, filll an Expected section only and leave room for an Actual section you will fill after you run the agents. for each ticket's Expected section, write in your own words: who the Boss should call first and why, all the agent delegations you expect - not boss calls everyone, which MCP tools you expect that run to use. 
plans that send every specialist on every ticket score low. you will compare this plan to what actually happens when your agents resolve the three tickets.

### What I was lacking after the first prompt

[What was missing or wrong after the first prompt, or "Nothing was lacking"]

### Prompt 2

[Paste the follow-up prompt here, or "n/a"]

## Section 7 — Problem 7: Backend routes

### Prompt 1

okay now for problem 7. the react frontend dashboard (the next problem) needs a backend to call. in backend/main.py use FastAPI and add routes that do the following. - return the three tickets and whether each is open or resolved. - take a ticket id and run your agent team on that ticket. - return recent agent events, what each agent said and which tools they used so the board can refresh. - approve a payment or purchase after a human clicks approve also agents only prepare the pay; this route is what actually changes cash. - return the current checking balance from cash_accounts - reset the database to the original values when you want to try a fresh run. From the backend folder start the server wtih uvicorn main:app --reload --port 8000 In output/harness.md list each route in one line (what url and what it does)

### What I was lacking after the first prompt

[What was missing or wrong after the first prompt, or "Nothing was lacking"]

### Prompt 2

[Paste the follow-up prompt here, or "n/a"]

## Section 8 — Problem 8: Agent dashboard

### Prompt 1

okay now for problem 8. build the frontend dashboard in frontend/ with React + Vite + Typescript. the page should call the routes built in problem 7. at minimum the board should: - list all three tickets, - let you pick one ticket and start the agent team on it. - show each agent and what they are saying/doing while the ticket runs - mark a ticket resolved when the run finishes, - show a short summary of what each agent did on that ticket. - let a human approve a pay or purchase when asked - show the checking balance (it should drop after an approved pay). make the dashboard look good be creative with the layout and feel. take inspo from how i suggested the ui for the last homeowrk 4 assignemtn. 
also tell the frontend to talk to the backend at https://localhost:8000 . on the backend allow the vite page origin usually https://localhost:5173 so the browser is allowed to call those routes. start the board wtih npm run dev. this open the react desk in your browser so u can pick tickets and watch agents. write output/design.md with what you chose for the dashboard look (layout, how agents read differentlty, how resolved tikcets and cash show up) and why including the creative choices that make it feel special and soemthing human would actually enjoy using

### What I was lacking after the first prompt

[What was missing or wrong after the first prompt, or "Nothing was lacking"]

### Prompt 2

[Paste the follow-up prompt here, or "n/a"]

## Section 9 — Problem 9: Resolve the tickets

### Prompt 1

okay now for problem 9. before testing the agents on a full run over the three tickets reset the working database data/campus_customs_new.db again so u start clean. note the starting checking balance. then run all three tickets on the board (101, 102, 103) until each is resolved. open output/desk_tickets.html from problme 6. on each ticket tab fill the Actual section from this run including which agents worked, what they delegated, and which tools they used. Keep your Expected section so u can compare the two. On the Cash tab of the same output/desk_tickets.html itemize the money including starting checking balance (after the reset), for each ticket how cash changed when that ticket resolved and why (which pay / purchase and dollar amount). and ending checking balance which must match cash_accounts in the working database. 
wrong cash math will lose points even if the baord shows the ticket as resolved. also save the following. output/resolved_tickets.json for each ticket: id, final status, short outcome, what each agent contributed, and any human approvals. output/resolved_board.html with a page you can double click with a screenshot of your react board for each resovled ticket (101,102,103). append real runs to output/audit_trail.json. Finsih output/harness.md so it covers tables, mcp tools, the five agents, api routes, the dashboard, and safety rules

### What I was lacking after the first prompt

[What was missing or wrong after the first prompt, or "Nothing was lacking"]

### Prompt 2

[Paste the follow-up prompt here, or "n/a"]

## Section 10 — Problem 10: Reflection

### Prompt 1

okay now for problem 10.  open output/desk_tickets.html and fill the Reflection tab. answer in your own vibe and be super detailed and super thorough:
how would you evaulate the performance of the agents on each ticket and why? for each ticket, how did Actual compare to the Expected plan you wrote earlier? What would have been simpler with one agent with tools and why? Also describe three new problems campus customs might face that this agent team could solve with the tools you built. also describe three new problems campus customs might face that this agent team could not solve with the tools you built and explain those tools and agent you would need to solve them. 
make sure you tie every answer to this app and the three tickets you ran. use the tickets tabs and cash tab on the same page as your evidence. Generic ai essays without campus customs details will score low. So make sure to add details about the app we built. be creative with your answers dont just give me basic answers but also make sure the answers easily align with what is asked and what is expected.

### What I was lacking after the first prompt

[What was missing or wrong after the first prompt, or "Nothing was lacking"]

### Prompt 2

[Paste the follow-up prompt here, or "n/a"]
