# TTB Label Verifier

A simple prototype which uses a vision language model (VLM) backend to extract specific fields from alcohol labels.

## Overview

This prototype allows for single label as well as bulk upload. The user first uploads at least one image and an optional CSV file containing the expected field values from the application. If only a single image is uploaded and no CSV is given, the user can input the application data manually, or select a "prediction only" option to just test the extraction process. A CSV must be given for bulk uploads (my assumption is that no one in their right mind would want to manually input this data image-by-image). 

In the next step, the app presents the verification results. There are several types of errors: 
 - Pass : extracted output matches application data (up to normalization)
 - Warning: For some fields, like ABV, we present a warning in cases where the numeric value matches but the text differs
 - Fail: If numeric values differ or there is not an exact match for specific fields (like gov warning; in this case, also match application data with hard coded ground truth)

 The main design consideration is that this system should consistently collect data on model errors in order to start creating a benchmark for evaluation. Therefore, when there is a field that does not match, the agent is asked to verify if the extracted label was correct or if not, what the correct value should be. Passing and non-passing fields are logged in order for future analysis and extraction. Additional information like prompt version, backend model, image hash, are also logged. 

 ### Other prototype features include:
 - Prediction only feature to test extraction
 - Selecting backend model
 - Sample files to test various test conditions and edge cases

 ### Requirements from instructions which are addressed:
 - Simple UI
 - Capable of bulk upload
 - Allows for various levels of matching (strict --> fuzzy for form fields) dependent on the field type
 - Abstracted API call allows for easy switching of model, or if an external API is not to be used, calls to a locally hosted model.
 - Logging of inference time (<3 sec usually)
 - Button to download test suite examples

 

 ### Limitations:
  - Mainly implemented the common elements across all beverage types
    - [TTB](https://www.ttb.gov/regulated-commodities/beverage-alcohol/beer/labeling/anatomy-of-a-malt-beverage-label-tool) shows specific formats for some fields like ABV percentage. These could be coded in as additional checks; for now the system just predicts the beverage type which can inform which patterns to use. 
  - Limitations in the images used for testing
    - Requirements specify that some images are distorted, poorly lit, etc. 
    - The system should is designed such that if there are VLM errors in extraction, that the agent can flag these.
    - Once enough data is collected, an offline evaluation can be used to better select backend models. In the meantime, the system allows for agents to manually override any errors. 
  - Prototype is totally anonymous
    - If we want to collect data and calculate agreement rates, match labels to annotators, etc. we would need to incorporate some sort of login/annotator ID system.


### Tools used:
  - System implemented using Claude Code
  - Simple HTML/JSS frontend, FastAPI backend
  - Anthropic vision API for processing


## Setup

### 1. Clone & install

```bash
cd treasury-ttb-project
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY
```

### 3. Run

```bash
uvicorn app.main:app --reload
```