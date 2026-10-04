# Multi-Agent Healthcare System using Google ADK

This project implements a multi-agent healthcare system using the **Google Agent Development Kit (ADK)**.  
It combines:

- Medical diagnosis support  
- Parallel mental health monitoring  
- Safety & ethics checks  

The system provides personalized, safe, and continuous care using specialized agents that collaborate in real time.

---

## 🌐 System Architecture

Our system consists of **3 MAIN AGENTS** (as shown in our PPT):

---

### 🟩 1️⃣ Medical Agent Cluster

**Responsible for:**
- Symptom analysis  
- Differential diagnosis  
- Personalized recommendations  
- Medical knowledge integration  

**Subagents:**
- Symptom Detective Agent  
- Clinical Reasoning Agent  
- Guidance Composer Agent  
- Knowledge Integration Agent  

---

### 🟧 2️⃣ Mental Health Agent

Runs **continuously in parallel** with the medical agent.

**Responsible for:**
- Emotion detection  
- Stress & anxiety scoring  
- Crisis monitoring  
- Empathy & support  

**Subagents:**
- Emotion Detection Agent  
- Stress & Anxiety Support Agent  
- Crisis Monitoring Agent  

---

### 🟥 3️⃣ Safety & Ethics Guard Agent

Ensures the system remains safe and responsible.

**Responsible for:**
- Medical safety checks  
- Risk detection  
- Emergency escalation  
- Overconfidence filtering  

**Subagents:**
- Medical Safety Checker  
- Risk Detection Agent  
- Escalation Manager  
- Overconfidence Guard  

---

## 🧠 Root Orchestrator

Although not counted as part of the “3 main agents,” the **Root Orchestrator** controls the entire conversation:

- Routes queries to the correct agent  
- Blends outputs  
- Ensures safety verification before responding  

---

## 🛠 Tools Used (ADK Tools Layer)

These tools support the agents:

- Patient Memory Tool  
- Medical Guidelines Lookup Tool  
- Symptom Extraction Tool  
- Emotion Analysis Tool  
- Risk Analysis Tool  
- Longitudinal Learning Engine  

Tools are implemented using Google ADK’s tool interface.

---

# 🔄 Workflow (How the System Works)

1. **User gives input**  
   Example: “I have chest pain and feel stressed.”

2. **Root Orchestrator activates**  
   Sends request to:  
   - Medical Agent Cluster  
   - Mental Health Agent  
   - Safety Agent  

3. **Medical Agent Cluster**  
   - Symptom Detective → asks follow-up questions  
   - Clinical Reasoning → generates possible conditions  
   - Knowledge Integration → checks medical guidelines  
   - Guidance Composer → provides safe recommendations  

4. **Mental Health Agent (Parallel)**  
   - Detects emotional distress  
   - Provides stress-reduction advice  
   - Monitors crisis signals  

5. **Safety & Ethics Guard**  
   - Checks for emergencies  
   - Ensures no harmful advice  
   - Overrides system if needed  

6. **Final Response by Orchestrator**  
   Combines:  
   - Medical output  
   - Mental health output  
   - Safety validation  
   - Patient’s memory  

7. **Memory Update**  
   Longitudinal engine stores:  
   - Symptoms  
   - Patterns  
   - Episode history  

---

# 🚀 Implementation Using Google ADK

### 1️⃣ Initialize project
```
adk init healthcare_system
```

### 2️⃣ Create the 3 main agents
```
adk generate agent MedicalAgentCluster
adk generate agent MentalHealthAgent
adk generate agent SafetyEthicsGuardAgent
```

### 3️⃣ Create subagents
(For medical, mental health, and safety modules)

### 4️⃣ Define tools
```
adk generate tool <ToolName>
```

### 5️⃣ Implement Root Orchestrator
Handles multi-agent routing and merging.

---

# 👥 Team
Add your team details here.

---

# 📜 License
MIT or your chosen license.
