from random import sample
import numpy
import os
from PIL import Image
from typing import Dict
from torch import LongTensor
import torch
torch.set_grad_enabled(False)
torch.set_num_threads(os.cpu_count())

from .load_params import convert_dalle_bart_torch_from_flax_params
from .min_dalle import MinDalle
from .models.dalle_bart_encoder_torch import DalleBartEncoderTorch
from .models.dalle_bart_decoder_torch import DalleBartDecoderTorch


class MinDalleTorch(MinDalle):
    def __init__(self, is_mega: bool, sample_token_count: int = 256):
        super().__init__(is_mega)
        print("initializing MinDalleTorch")

        print("loading encoder")
        self.encoder = DalleBartEncoderTorch(
            layer_count = self.config['encoder_layers'],
            embed_count = self.config['d_model'],
            attention_head_count = self.config['encoder_attention_heads'],
            text_vocab_count = self.config['encoder_vocab_size'],
            text_token_count = self.config['max_text_length'],
            glu_embed_count = self.config['encoder_ffn_dim']
        )
        encoder_params = convert_dalle_bart_torch_from_flax_params(
            self.model_params.pop('encoder'), 
            layer_count=self.config['encoder_layers'], 
            is_encoder=True
        )
        self.encoder.load_state_dict(encoder_params, strict=False)

        print("loading decoder")
        self.decoder = DalleBartDecoderTorch(
            image_vocab_size = self.config['image_vocab_size'],
            image_token_count = self.config['image_length'],
            sample_token_count = sample_token_count,
            embed_count = self.config['d_model'],
            attention_head_count = self.config['decoder_attention_heads'],
            glu_embed_count = self.config['decoder_ffn_dim'],
            layer_count = self.config['decoder_layers'],
            batch_count = 2,
            start_token = self.config['decoder_start_token_id'],
            is_verbose = True
        )
        decoder_params = convert_dalle_bart_torch_from_flax_params(
            self.model_params.pop('decoder'), 
            layer_count=self.config['decoder_layers'],
            is_encoder=False
        )
        self.decoder.load_state_dict(decoder_params, strict=False)

        if torch.cuda.is_available(): 
            self.encoder = self.encoder.cuda()
            self.decoder = self.decoder.cuda()
            self.detokenizer = self.detokenizer.cuda()


    def generate_image_tokens(self, text: str, seed: int) -> LongTensor:
        text_tokens = self.tokenize_text(text)
        text_tokens = torch.tensor(text_tokens).to(torch.long)
        if torch.cuda.is_available(): text_tokens = text_tokens.cuda()

        print("encoding text tokens")
        encoder_state = self.encoder.forward(text_tokens)

        print("sampling image tokens")
        torch.manual_seed(seed)
        image_tokens = self.decoder.forward(text_tokens, encoder_state)
        return image_tokens
        

    def generate_image(self, text: str, seed: int) -> Image.Image:
        image_tokens = self.generate_image_tokens(text, seed)
        print("detokenizing image")
        image = self.detokenizer.forward(image_tokens).to(torch.uint8)
        image = Image.fromarray(image.to('cpu').detach().numpy())
        return image