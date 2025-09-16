
<h1 align="center"> <img src="assets/caller.jpg" alt="AgentScaler Logo" width="35" style="vertical-align: middle; margin-right: px;">AgentScaler: 

Towards General Agentic Intelligence via Environment Scaling</h1>

## Table of Contents

- 🌟[Overview](#overview)
- 🔧[Installation](#installation)
- 📚[World Knowledge Build](#world-knowledge-build)
- 📉[Model Training](#model-training)
- 🧐[Evaluation](#evaluation)
- 🚩[Citation](#citation)

---




## 🌟Overview

In this work, we scale up environments as a step
towards advancing general agentic intelligence. This gives rise to two central
challenges: (i) how to scale environments in a principled manner, and (ii) how
to effectively train agentic capabilities from experiences derived through inter-
actions with these environments. To address these, we design a scalable frame-
work that automatically constructs heterogeneous environments that are fully
simulated, systematically broadening the space of function-calling scenarios.
We further adapt a two-phase agent fine-tuning strategy: first endowing agents
with fundamental agentic capabilities, then specializing them for domain-
specific contexts. Extensive experiments on agentic benchmarks, τ-bench,
τ2-Bench, and ACEBench, demonstrate that our trained model, AgentScaler,
significantly enhances the models’ function-calling capability.

## 🔧Framework
We introduce a principled pipeline that comprises two central stages: (i) fully simulated
environment construction and scaling, which establishes and expands diverse agentic scenarios, and (ii)
agent experience learning, which exploits these environments to foster generalizable intelligence.
![Framework Overview](assets/env_build.png "Click to see the detailed architecture")

The process to obtain the agent trajectories
![Framework Overview](assets/infer.png "Click to see the detailed architecture")


## 📚MainResults
Main results on τ-bench, τ2-Bench, and ACEBench-en
![Main Results](assets/main.png "Click to see the detailed architecture")




## 🚩Citation

Please cite our repository if you think it's useful

```bibtex

```



## 🎉Contributors


We will offer long-term maintenance to fix bugs and solve issues. So if you have any problems, please put issues to us.