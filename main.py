import utime
import machine
import usocket as socket
import network
import _thread
import json

#Bargraph constants
FINE_TIMESTEP = 6
COARSE_TIMESTEP = 7
RAVG_DEPTH = 2

#Maya's constants
WEEK_TIMESTEP = FINE_TIMESTEP*COARSE_TIMESTEP
TOTAL_TIME = RAVG_DEPTH*WEEK_TIMESTEP
HYST_RANGE = 10000 #Hysteresis +/- range, affects on/off sensitivity.
HYST_OFFSET = 0 #Hysteresis midpoint offset.
IR_THRESHOLD_HIGH = 2**15 + HYST_OFFSET + HYST_RANGE
IR_THRESHOLD_LOW = 2**15 + HYST_OFFSET - HYST_RANGE #These should be double-checked to ensure the hysteresis works at the desired range. !!!!!!!


MAX_RATE = 50 #Esme's constants

COEFFICIENT = 50 #Seb constants. Coefficient for the Resistance_to_Celsius function. May be determined experimentally using a thermometer.  

#Pin configuration
adcPin = machine.ADC(26)
obLed = machine.Pin('WL_GPIO0', machine.Pin.OUT)
actuatorPin = [machine.Pin(i,machine.Pin.OUT) for i in range(6,10)] #6 and 7 will be the presence/absence for the IR sensors, 8 and 9 will be the heating elements. '10' is not actually in this list; it's just there for the range function.
pinOut = [machine.Pin(i,machine.Pin.OUT) for i in range (10,16)]

# Bargraph global variables.
m_dataRecord = [[0.0 for i in range(WEEK_TIMESTEP)] for j in range(RAVG_DEPTH)] #Bargraph data record. This is the master copy: outer is week number, inner is timestamp number.
timestamp = 0 #Integer tracking the current timestep in the week, ranging from 0 to TOTAL_TIME-1.
m_irStatus = [0,0] #Gives the current TRUE/FALSE status of whether the IR sensor is detecting anyone.
m_bargraph = [0.0 for i in range(WEEK_TIMESTEP)] #Bargraph output

#Esme's results
e_flowrate = [0.0,0.0]

#sebastian's results
s_Temperature = [0.0,0.0] #records the current temperature at thermistor 1 and 2

#Maya's functions
    
shutdown = False

def m_IRsensor(m_irID):
    adcValue = 2**16 - adcPin.read_u16() #Invert the ADC value, since HIGH = no detection and LOW = detection.
    if(m_irStatus[m_irID]==0): #hysteresis to prevent flickering value near a single threshold.
        m_irStatus[m_irID] = (adcValue>IR_THRESHOLD_HIGH)
    elif(m_irStatus[m_irID]==1):
        m_irStatus[m_irID] = (adcValue>IR_THRESHOLD_LOW)
    if(m_irStatus[m_irID]): #Update the status of the corresponding actuator pin.
        actuatorPin[m_irID].on()
    else:
        actuatorPin[m_irID].off()

def m_minmax(data):
    output = [0.0,0,float(COEFFICIENT),0]
    for i in range(len(data)):
        c = data[i]
        if(c>output[0]):
            output[0]=c
            output[1]=i
        elif(c<output[2]):
            output[2]=c
            output[3]=i
    return output

def m_bars_day(m_day_response): #Writes the bars for a single day.
    bars = []
    bars.append("""<td><span class="bar" style="height: 150px; width: 0px; opacity: 0;"></span>""")
    for i in range(len(m_day_response)):
        data = m_day_response[i]
        red_norm = int(220*(data/MAX_RATE)) #Normalizes the observed flow rates to a number out of 255, to help with colour generation.
        blue_norm = int(255-red_norm)
        snip = """<span class="bar" style="height: {data}; background-color: #{red_norm:02x}44{blue_norm:02x}"></span>""".format(data=data,red_norm=red_norm,blue_norm=blue_norm)
        bars.append(snip)
    bars.append("</td>")
    return "".join(bars)

def m_peak_day(m_day_response):
    data_txt = []
    data_txt.append("""<td>""")
    data = m_day_response
    data_minmax = m_minmax(data)
    #data_minmax = [max(data),max(range(len(data)), key=data.__getitem__),min(data),min(range(len(data)), key=data.__getitem__)] #Might need to alter this since this seems to think lists can't use __getitem__
    #data_flow = data[1]%13+2 # Need to be able to pull out the flow rate and attendance data from Esme's results and mine.
    #data_attendance = data[1]%31+7
    snip = """Max Temp: {max} ({tmax}:00)<br>Min Temp: {min} ({tmin}:00)""".format(max=data_minmax[0],tmax=data_minmax[1],min=data_minmax[2],tmin=data_minmax[3])
    data_txt.append(snip)
    data_txt.append("""</td>""")
    return "".join(data_txt)



#Esme functions
        
def get_resistance(): 
#function to get resistance value from photoresistor
    resistance_val = (adcPin.read_u16()) 
    return resistance_val
def flow_rate(resistance_val): 
#function that calculates the flow rate of the water based on the resistance found by the get_resistance function	
    water_flow = (resistance_val*MAX_RATE)/(2**16) 
    return water_flow

#Sebastian functions

#Function: s_CollectTemperatureData
#Purpose: Collects the 16-bit value reading from the ADC pin, then calls the Resistance_to_Celsius conversion function and places it inside of the variable "result."
#Parameters: Takes no parameters.
#Return: Returns the calculated result, which should be a temperature in celsius. 
def s_CollectTemperatureData(): 
    
    adc = adcPin.read_u16()
    
    result = Resistance_to_Celsius(adc,COEFFICIENT)
    
    return result


#Function: Resistance_to_Celsius:
#Purpose: Converts an inputted 16-bit value to a range up to 50. Intended for use with the ADC pin and thermistor 16-bit resistance readings. Converts them to Celsius. 
#Parameters: thermistor_resistance: 16-bit value input. Intended to be sourced from the ADC reading of the thermistor.
#		     coefficient: Conversion coefficient that dictates what the value the 16-bit input is converted to. May be determined experimentally with a thermometer.
#Return: Returns the calculated temperature.

def Resistance_to_Celsius(thermistor_resistance, coefficient):
    Temperature = thermistor_resistance*coefficient/(2**16)
    
    return Temperature

#Is there a function to actually encode switching the heating elements off and on? !!!!!!!

#Purpose: Sets the heater status for a given shower to on or off based on the parameters it was passed
#Parameters: int pindex: GPIO output pin array index number that correlates to a given shower heater
#             float threshold: The temperature threshold for a shower. Inteneded to correlate to the pin and taken from the UI.
#             float temperature: The current temperature from a thermometer. Intended to correlate to the above shower. 
#Return: Returns the string "on" if the temperature is less than the threshold minus two, and off if it is greater than that, or if it is greater than the threshold overall.

def set_heater_status(pindex, threshold, temperature):
    #Checks if pin is on or off. 
    if(actuatorPin[pindex].value()):
        #If on, switches pin off if it is GREATER than the threshold, else stays on and returns on.
        if(temperature > threshold):
            actuatorPin[pindex].off()
            return "off"
        else:
            return "on"
    else:
    #If it is off, it switches the pin on if it is LESS than the threshold minus two
        if(temperature < (threshold - 2)):
            actuatorPin[pindex].on()
            return "on"
        else:
            return "off"


#Purpose: Finds a specified query from a given URL after being fed the starting character and designated ending character. This function assumes all queries have unique ascii starting characters.
#Parameters: str URL: Full current URL string
#             char query_start_indicator: The character that denotes the start of your query string segment. Will not be included in the taken string.
#             char query_end_indicator: The character that denotes the end of your query string segment. Will not be included in the taken string.
#Return: Returns a truncated int that is the extracted value from the specified URL query.

def get_url_query(URL, query_start_indicator, query_end_indicator):
    
    querystring = ""
    
    #means that the current character is between the start and end indicator
    inQuery = False
    
    for char in URL:
        if (char == query_start_indicator):
            inQuery = True
        elif (char == query_end_indicator):
            break;
        
        if (inQuery):
            querystring += char
    
    #now you have the query string, so find the equals sign in the query string
    querystring_as_list = querystring.split("=")
    query_value = int(float(querystring_as_list[1]))
    
    return query_value


#Main sensor-checking function

def pollSensors(sensorID):
    global e_flowrate
    global s_Temperature
    #Each sensor check turns on a GPIO for a transistor feeding the ADC. 5us are given as a buffer, the values are read, and then the pin is switched off. This is done once for each sensor.
    #print(sensorID)
    if(sensorID == 0): #Maya code!
        pinOut[0].on()
        utime.sleep_us(5)
        m_IRsensor(0)
        pinOut[0].off()
        
        pinOut[1].on()
        utime.sleep_us(5)
        m_IRsensor(1)
        pinOut[1].off()
    elif(sensorID == 1): #Esme code!
        pinOut[2].on()
        utime.sleep_us(5)
        resistance_val = get_resistance()
        water_flow = flow_rate(resistance_val)
        e_flowrate[0]=water_flow
        pinOut[2].off()
        
        pinOut[3].on()
        utime.sleep_us(5)
        resistance_val = get_resistance()
        water_flow = flow_rate(resistance_val)
        e_flowrate[1]=water_flow
        pinOut[3].off()
    elif(sensorID == 2): #Sebastian code!
        pinOut[4].on() 
        utime.sleep_us(5)
        s_Temperature[0] = s_CollectTemperatureData()
        pinOut[4].off()
        pinOut[5].on()
        utime.sleep_us(5)
        s_Temperature[1] = s_CollectTemperatureData()
        pinOut[5].off()


#Beginning of core functions.

def picoHardwareLoop():
    print("Hardware loop!")
    global shutdown
    global adcPin
    global m_dataRecord
    global m_bargraph
    global timestamp
    #global obLed
    while not shutdown:
        #print(".")
        pollSensors(0) #maya's sensors
        pollSensors(1) #esme's sensors
        pollSensors(2) #seb's sensors
        
        #Update the bar-graph record as the sum of flow rates.
        m_dataRecord[timestamp//WEEK_TIMESTEP][timestamp%WEEK_TIMESTEP] = (e_flowrate[0]+e_flowrate[1])
        #Calculate the rolling average for the current time ID only. Other values don't need to be recalculated.
        m_ravg = 0.0 #Temporary value, does not need to leave scope.
        for i in range(RAVG_DEPTH):
            m_ravg = m_dataRecord[i][timestamp%WEEK_TIMESTEP]
        m_bargraph[timestamp%WEEK_TIMESTEP] = m_ravg/RAVG_DEPTH
        timestamp += 1
        
        if(timestamp>=TOTAL_TIME):
            timestamp = 0
        
        #PLACEHOLDER: Update actuators
            
        #PLACEHOLDER: Push results to webpage-exposed API. Note: This might not be necessary; since it's running in a separate thread, the results can be dynamically accessed so long as they're global variables.
        utime.sleep(5)
    print("Exiting Hardware Loop")
    
def get_status(): #Intakes the status of things we want to push to the webpage as a dictionary and then returns it as a json to be pushed. This is the main Pico -> Webpage API.
    status = {
        "temp1": s_Temperature[0],
        "temp2": s_Temperature[1],
        "flow1": e_flowrate[0],
        "flow2": e_flowrate[1],
        "irdtct": (m_irStatus[0]+m_irStatus[1]) #number of people present
    }
    return json.dumps(status)

def web_page(m_data):
    bar_width = 8
    m_bars_data = []
    m_text_data = []
    for i in range(COARSE_TIMESTEP): #Counts off each day, from 0 to 6.
        dayslice = [m_data[j] for j in range(i*FINE_TIMESTEP,(i+1)*FINE_TIMESTEP)]
        print("Printing bars,", dayslice)
        m_bars_data.append(m_bars_day(dayslice)) #These need to pass m_bars_day and m_peak_day the relevant data from m_bargraph. Do I need to take a slice?
        m_text_data.append(m_peak_day(dayslice))
    m_bars_data = "\n".join(m_bars_data)
    m_text_data = "\n".join(m_text_data)
    html = """<html><head>
    <title>Pico Web Server</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="icon" href="data:,">
    <style>
    .barbox {{text-align: center; vertical-align: middle;}} /*Generic centering class for non-graphic elements of the graph section*/
    .bar {{height: 150px; width: {bar_width}px; display: inline-block; background-color: #004499; padding: 0px;}} /*The bar element of the graph section, gets procedurally generated by python templating*/
    .bartext {{font-family: "Times New Roman", Times, serif;}} /*Format class for the text data on row 3 of the graph*/
    .box {{border: 2px solid black; padding: 10px; background-color:white; color:black; width:100px; height:75px; margin: 0 auto; align-items:center; justify-content:center; display:inline-block;}} /* Dictates the colour, width, height alignment of contents, and other relevant details of the black boxes used in the second row of the table */
    </style>
    </head>
      <body>
        <table style="width:50%; text-align: center;"> 
            <tr> <!--First row of the table - each cell describes the value in the second row of that column-->
            <td>Current Avg Temp</td>
            <td>Heater Status</td>
            <td>Showers in Use</td>
            <td>Water Usage</td>
            </tr>
            <tr> <!--Start of the second row of the table - contains data collected by the sensors-->
            <td>
                <div style="font-size:170%" class="box"> <!--Div for water temperature value, declares font size and adds box-->
                35&deg;C <!--The temperature data from the thermistor will be displayed here-->
                </div>
            </td>
            <td>
                <div style="font-size:170%" class="box"> <!--Div for the heater status, declares font size and adds box-->
                OFF <!--States whether the heater is on/off-->
                </div>
            </td>
            <td>
                <div style="font-size:170%" class="box"> <!--Div for the number of showers currently in use, declares font size and adds box-->
                3 <!--The IR sensor will detect how many showers are in use and the number will be displayed here-->
                </div>
            </td>
            <td>
                <div style="font-size:170%" class="box"> <!--Div for the current water usage, declares font size and adds box-->
                27 L/min <!--Amount of water being used in L/min, will be calculated using data from photoresistor-->
                </div>
            </td>
            
        </table>
<table border = "1" width = 50%> <!--Beginning of table containing the graph-->
    <tr class="barbox"><td>Sunday</td><td>Monday</td><td>Tuesday</td><td>Wednesday</td><td>Thursday</td><td>Friday</td><td>Saturday</td></tr>
    <tr class="barbox">
    <!--The element below constitutes each bar of the graphs in order, separated by cell. It was populated by Python templating.-->
    <!--The first row is the bar graphs of temperature themselves, representing averages over intervals of the day.-->
    <!--The second row is relevant daily information about each day's data.-->
    {m_bars_data}
    </tr>
    <tr class="bartext"> <!--A textual report of relevant statistics from each day-->
    {m_text_data}
    </tr>
    </table>
<br>


        <!--Sebastian's HTML Section-->

    <div style="background-color:#DDDDDD">
    <h3>The following section is restricted to technicians only:</h3>
    <!--<center>-->
    <!--This style segment defines larger horizontal spacing for the table. It's too crowded otherwise-->  
    <style>
    .slider {{width: 100%;}}
    table, th, td {{}}
    th, td {{
      padding-left: 20px;
      padding-right: 20px;
      
    }}
    </style>

          <!--Shower 1 info table here.-->  
      <table>
        <tr>
          <th><h3>Shower 01</h3></th>
        </tr>
        <tr>
          <td>Status:</td>
          <td>In Use/Vacant</td> <!--One of these will be selected depending on the IR status-->  
          <td style="text-align:center;">HOT Threshold</td> 
        </tr>
          <tr>
          <td></td>
          </tr>
        <tr>
          <td>Water Temperature:</td>
          <td>{s_Temperature[0]}°C</td><!--This is where the temperature of the water for the current shower will go-->  
          <td><input type="range" min="0" max="50" value="40" class="slider" id="threshold1">10°C <span style="float:right">50°C</span></td>
          
          <!--Later, this and other sliders like it will relay the selected value back to the pico to change the threshold that enables the inline heating system-->  
          
          <td style="border:1px solid black;"><span id="value1"></span>°C</td> 
          
          
          <!--This is where the value of the current HOT threshold for the shower is, based on the slider selection-->
          
        </tr>
        <tr>
        <td></td>
        </tr>
        <tr>
          <td>Heater Status:</td>
          <td>On/Off</td> <!--One of these will be selected based on the heater status, which may be its own variable or extrapolated based on current temperature and threshold. I believe the former is more appropriate-->  
        </tr>   
      </table> 
      
      <br>
      <br>
      
      <!--Shower 2 info table here. This is indentical to the first shower table, however values may vary.-->  
      <table>
        <tr>
          <th><h3>Shower 02</h3></th>
        </tr>
        <tr>
          <td>Status:</td>
          <td>In Use/Vacant</td>
          <td style="text-align:center;">HOT Threshold</td>
        </tr>
          <tr>
          <td></td>
          </tr>
        <tr>
          <td>Water Temperature:</td>
          <td>{s_Temperature[1]}°C</td>
          
          <td><input type="range" min="0" max="50" value="40" class="slider" id="threshold2">10°C <span style="float:right">50°C</span></td>
          
          <td style="border:1px solid black;"><span id="value2"></span>°C</td>
        </tr>
        <tr>
        <td></td>
        </tr>
        <tr>
          <td>Heater Status:</td>
          <td>On/Off</td>
        </tr>
      </table>  
      <!--</center>-->
      <br>
      <br>
      <br>
  </div>

    <script>
  const queryParams = window.location.search;
  const URLParams = new URLSearchParams(window.location.search);
  var slider = document.getElementById("threshold1");
  var output = document.getElementById("value1");
  var slider2 = document.getElementById("threshold2");
  var output2 = document.getElementById("value2");
  slider.value = URLParams.get('threshold1');
  slider2.value = URLParams.get('threshold2');

  //For Updating the URL:
  function updateURL(){{
  var slidervalue1 = document.getElementById("threshold1").value; //These get the threshold values.
  var slidervalue2 = document.getElementById("threshold2").value;

  var baseUrl = window.location.href.split('?')[0]; //This stores the current URL
  var newUrl = baseUrl + "?threshold1=" + encodeURIComponent(slidervalue1) + "&threshold2=" + encodeURIComponent(slidervalue2); //This attaches the threshold values to a new URL

  
  //This updates the URL at the top
  //Maya's note: it updates the URL but didn't actually push the results to the server; for now I'll use replace() to ensure it gets pushed, and I'll try to find a less clunky way to implement it after, if there's time.
  //window.history.pushState({{ path: newUrl }}, '', newUrl);
  window.location.replace(newUrl);

  }}

  //updateURL();

  output.innerHTML = slider.value;
  output2.innerHTML = slider2.value;

  slider.oninput = function() {{
    output.innerHTML = this.value;
  }}

  slider2.oninput = function() {{
    output2.innerHTML = this.value;
  }}

  slider.addEventListener("change",(event) => {{updateURL();}})
  slider2.addEventListener("change",(event) => {{updateURL();}})

  

  </script>


    </body>
    </html>""".format(m_bars_data=m_bars_data,m_text_data = m_text_data, bar_width=bar_width, s_Temperature = s_Temperature)
    return html

def send_response(conn, headers, body, max_attempts = 10):
    headlen = 0
    attempts = 0
    while headlen < len(headers) and attempts < max_attempts:
        headlen += conn.send(headers[headlen:])
        print("Sent {}/{} bytes of headers".format(headlen, len(headers)))
        attempts += 1
    
    if headlen < len(headers):
        raise RuntimeError("Failed to send headers after {} attempts".format(attempts))
    
    bodylen = 0
    attempts = 0
    while bodylen < len(body) and attempts < max_attempts:
        bodylen += conn.send(body[bodylen:])
        print("Sent {}/{} bytes of body".format(bodylen, len(body)))
        attempts += 1
        
    if bodylen < len(body):
        raise RuntimeError("Failed to send body after {} attempts".format(attempts))
    
#Seb's new global variables:
threshold_q_start_indi = ["?","&"] #index 0 for shower 1, index 1 for shower 2
shower_temp_threshold = [1,1]
shower_actuator_pindex = [actuatorPin[2],actuatorPin[3]]


def main():
    global shutdown
    print("Booting up...")
    hardwarethread = _thread.start_new_thread(picoHardwareLoop,())
    print("Created hardware loop thread {}".format(hardwarethread))

    # Create a network connection
    ssid = 'RPI_PICO_AP'       #Set access point name 
    password = '12345678'      #Set your access point password
    ap = network.WLAN(network.AP_IF)
    ap.config(essid=ssid, password=password)
    ap.active(True)            #activating

    while ap.active() == False:
        pass
    print('Connection is successful')
    print(ap.ifconfig())

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('', 80))
    s.listen(5)
    
    while not shutdown:


        try:
            #Beginning of websocket working document.
            conn,addr = s.accept()
            print('Got a connection from %s' % str(addr))
            request = conn.recv(1024)
            if request:
                request = str(request)
                print('Request Content = {}\n'.format(request))
                shower_temp_threshold[0] = get_url_query(request,threshold_q_start_indi[0],threshold_q_start_indi[1])
                shower_temp_threshold[1] = get_url_query(request,threshold_q_start_indi[1]," ")
                print("The threshold values for the showers are", shower_temp_threshold[1],"and", shower_temp_threshold[0],"respectively.")
        
                shower1_status = set_heater_status(shower_actuator_pindex[0], shower_temp_threshold[0], s_Temperature[0])
                shower2_status = set_heater_status(shower_actuator_pindex[1], shower_temp_threshold[1], s_Temperature[1])

            # if buzzer_on == 6: #Interprets the results of the query evaluation. This will not compile in its current state; this is example code. !!!!!!!
            #     print('BUZZER ON')
            #     redLED_pin.value(1)
            # elif buzzer_off == 6:
            #     print('BUZZER OFF')
            #     redLED_pin.value(0)
            try:
                # pushes the json from get_status() to the webpage.
                if request.find("/status") == 6:
                    print("getting status")
                    response = get_status()
                    conn.sendall("HTTP/1.1 200 OK\n")
                    conn.sendall("Content-Type: application/json\n")
                    conn.sendall("Connection: close\n\n")
                    conn.sendall(response)
                else:
                    print("getting webpage")
                    response = web_page(m_bargraph)
                    print("sending status ({} bytes)".format(len(response)))
                    headers = ["HTTP/1.1 200 OK", "Content-Type: text/html", "Content-Length: {}".format(len(response)), "Connection: close"]
                    headerstr = "\n".join(headers) + "\n\n"
                    send_response(conn, headerstr, response, 25)

            except Exception as e:
                conn.sendall(b"HTTP/1.1 500 Internal Server Error\n")
                print(e)
                raise
            finally:
                print("finished sending data")
                conn.close()
                #utime.sleep(1)
        except KeyboardInterrupt:
            print("Shutting down...")
            shutdown = True
    s.close()
    
main()






