import torch
import transformers
from langchain.chains import RetrievalQA
from langchain.document_loaders import PyPDFLoader
from langchain.embeddings.huggingface import HuggingFaceEmbeddings
from langchain.llms import HuggingFacePipeline
from langchain.text_splitter import CharacterTextSplitter
from langchain.vectorstores import Qdrant
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TextStreamer,
)
import time


def process_pdf(filepath):
    global retrieval_chain
    # Loading and splitting the document
    loader = PyPDFLoader(filepath)
    docs = loader.load_and_split()
    # Chunk text
    text_splitter = CharacterTextSplitter(chunk_size=500, chunk_overlap=100)
    chunked_documents = text_splitter.split_documents(docs)

    # Load chunked documents into the Qdrant index
    db = Qdrant.from_documents(
        chunked_documents,
        HuggingFaceEmbeddings(model_name="multi-qa-mpnet-base-dot-v1"),
        location=":memory:",
    )
    retriever = db.as_retriever()
    retrieval_chain = RetrievalQA.from_llm(llm=llama_llm, retriever=retriever)


start_time = time.time()

# Load the Llama-2 Model
model_name = "Breeze-7B-32k-Instruct-v1_0"
tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
tokenizer.pad_token = tokenizer.eos_token
tokenizer.padding_side = "right"
streamer = TextStreamer(tokenizer=tokenizer, skip_prompt=True)

model = AutoModelForCausalLM.from_pretrained(
    model_name,
    device_map="auto",
    low_cpu_mem_usage=True,  # try to limit RAM
    quantization_config=BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
    ),  # load model in low precision to save memory
    # attn_implementation="flash_attention_2",
)

# Building a LLM QNA chain
text_generation_pipeline = transformers.pipeline(
    model=model,
    tokenizer=tokenizer,
    task="text-generation",
    temperature=0.2,
    repetition_penalty=1.1,
    return_full_text=True,
    max_new_tokens=300,
    streamer=streamer,
)

llama_llm = HuggingFacePipeline(pipeline=text_generation_pipeline)
retrieval_chain = None
print("\nLoad model time: %.2fs\n" % (time.time() - start_time))

start_time = time.time()
process_pdf("CNS16190-zh_TW.pdf")
print("\nprocess_pdf time: %.2fs\n" % (time.time() - start_time))

while True:
    # 用中文列舉所有cns16190的適用範圍
    query = input("enter query: ")
    
    start_time = time.time()
    response = retrieval_chain.run(query)

    # Extract only the necessary part from the response
    start_idx = response.find("Helpful Answer: ")
    if start_idx != -1:
        response = response[start_idx + len("Helpful Answer: ") :]

    print(response)
    print("\nInference time: %.2fs\n" % (time.time() - start_time))