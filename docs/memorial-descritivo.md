# Memorial descritivo — ColdTrack Edge

## 1. Descrição do Projeto

O ColdTrack Edge é um protótipo de nó sensor IoT desenvolvido para o monitoramento das condições ambientais durante o transporte refrigerado de mercadorias, com aplicação voltada principalmente à cadeia logística de produtos agrícolas do Vale do São Francisco, como manga e uva.

O objetivo é acompanhar temperatura e umidade relativa do ar no interior do compartimento refrigerado, permitindo identificar condições que possam comprometer a conservação e a qualidade da carga durante o transporte.

## 2. Funcionamento

O protótipo utiliza um ESP32-C3 conectado a um sensor DHT11, responsável pela medição de temperatura e umidade. O microcontrolador processa as leituras localmente e utiliza três LEDs como indicadores visuais:

- 🟢 Verde: condição normal;
- 🟡 Amarelo: condição de atenção;
- 🔴 Vermelho: condição crítica ou falha de leitura.

Os limites dependem do perfil da carga (por exemplo manga ou uva), cadastrado na API e enviado ao sensor a cada leitura; o perfil demonstrativo (normal até 15 °C, atenção até 20 °C) vale para sensor sem veículo.

Por meio de uma conexão Wi-Fi, as leituras são enviadas a cada 20 segundos, em JSON por HTTPS, para uma API em Azure Functions, que as classifica pela faixa da carga e grava no Azure Cosmos DB. Cada leitura traz temperatura, umidade relativa e intensidade do sinal Wi-Fi (RSSI). Sem rede, as leituras ficam guardadas na memória flash da placa e são reenviadas quando a conexão volta. O envio ao ThingSpeak por MQTT é opcional e ficou como experimento e para a tela de demonstração do painel.

## 3. Aplicação no Negócio

O dispositivo poderá ser instalado no interior de baús, carretas e contêineres refrigerados, permitindo acompanhar as condições do microclima ao qual a mercadoria está submetida.

No contexto do agronegócio de Petrolina e Juazeiro, a solução pode contribuir para a rastreabilidade da cadeia fria durante o transporte de frutas e outros produtos sensíveis às variações ambientais.

## 4. Design Circular

Como parte dos princípios de Design Circular e Upcycling, o protótipo físico será acondicionado em um gabinete construído com material reaproveitado. O gabinete possuirá abertura para alimentação USB-C e áreas de ventilação próximas ao sensor, permitindo a circulação de ar necessária às medições.

## 5. Limitações

O DHT11 é adequado para demonstrações e prototipagem, porém possui limitações de precisão, resolução e tempo de resposta quando comparado a sensores industriais. Também não é indicado para exposição direta à condensação.

A comunicação por Wi-Fi depende da existência de uma rede disponível, sendo uma limitação importante para veículos em deslocamento. Uma versão comercial poderia utilizar comunicação celular, LoRaWAN ou outra tecnologia apropriada, além de armazenamento local para períodos sem conectividade.

O gabinete produzido por reaproveitamento de materiais também não possui grau de proteção IP certificado, não devendo ser considerado equivalente a um invólucro industrial.

## 6. Evolução do Projeto

Os dados já são integrados ao Microsoft Azure, com armazenamento histórico, alertas e painel web (repositório [Front-End-pi](https://github.com/mbalbuquerque/Front-End-pi)). Fica como etapa futura o uso de modelos preditivos para identificação de riscos à qualidade das mercadorias; há uma análise climática preliminar da rota em `analise/`.

O fluxo implementado é:

```
Sensor → ESP32-C3 → processamento Edge → Wi-Fi → HTTPS → Azure Functions → Cosmos DB → painel web
```

O ColdTrack Edge, portanto, funciona como uma prova de conceito para demonstrar a aquisição, processamento e transmissão de dados ambientais aplicados ao monitoramento da cadeia fria no transporte de mercadorias.
