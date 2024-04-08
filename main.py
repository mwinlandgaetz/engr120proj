import utime
import machine
import usocket as socket
import network
import json
import gc #Added a garbage collection library because I was having some memory management problems.

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


MAX_RATE = 50 #Esme's constants - estimated max rate of water flowing from showers, used in flow_rate function to convert the flow rate into L/min.

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
e_flowrate = [0.0,0.0] #records the values detected by both photoresistors
shower1_status = "Off"
shower2_status = "Off"

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

def m_minmax(data): #Simple function that computes the minimum and maximum of the data passed by m_peak_day().
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

def m_bars_day(m_day_response): #Writes the bars for a single day as HTML.
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

def m_peak_day(m_day_response): #Assembles the min/max into HTML. 
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
#function that calculates the flow rate of the water in L/min based on the resistance found by the get_resistance function	
    water_flow = (resistance_val*MAX_RATE)/(2**16) 
    return water_flow
def heater_status(shower1_status, shower2_status):
#function to determine whether the heater is on or off 
    if shower1_status == "On" or shower2_status == "On":
        return "ON"
    else:
        return "OFF"

#Sebastian functions

#Function: Resistance_to_Celsius:
#Purpose: Converts an inputted 16-bit value to a range up to 50. Intended for use with the ADC pin and thermistor 16-bit resistance readings. Converts them to Celsius. 
#Parameters: thermistor_resistance: 16-bit value input. Intended to be sourced from the ADC reading of the thermistor.
#		     coefficient: Conversion coefficient that dictates what the value the 16-bit input is converted to. May be determined experimentally with a thermometer.
#Return: Returns the calculated temperature.

def Resistance_to_Celsius(thermistor_resistance, coefficient):
    Temperature = thermistor_resistance*coefficient/(2**16)
    
    return Temperature


#Function: s_CollectTemperatureData
#Purpose: Collects the 16-bit value reading from the ADC pin, then calls the Resistance_to_Celsius conversion function and places it inside of the variable "result."
#Parameters: Takes no parameters.
#Return: Returns the calculated result, which should be a temperature in celsius. 
def s_CollectTemperatureData(): 
    
    adc = adcPin.read_u16()
    
    result = Resistance_to_Celsius(adc,COEFFICIENT)
    
    return result


#Is there a function to actually encode switching the heating elements off and on? !!!!!!!

#Function: set_heater_status
#Purpose: Sets the heater status for a given shower to on or off based on the parameters it was passed
#Parameters: int pindex: GPIO output pin array index number that correlates to a given shower heater
#             float threshold: The temperature threshold for a shower. Inteneded to correlate to the pin and taken from the UI.
#             float temperature: The current temperature from a thermometer. Intended to correlate to the above shower. 
#Return: Returns the string "on" if the temperature is less than the threshold minus two, and off if it is greater than that, or if it is greater than the threshold overall.

def set_heater_status(pindex, threshold, temperature): #Switches the heater status on or off depending on the temperature at the thermistor and the threshold values.
    status = [shower1_status,m_irStatus[0]] if (pindex == 2) else [shower2_status,m_irStatus[1]]
    #Checks if pin is on or off. 
    if(status[1] == 0): return "Off"
    if(status[0].lower() == "on"):
        #If on, switches pin off if it is GREATER than the threshold, else stays on and returns on.
        if(temperature > threshold):
            actuatorPin[pindex].off()
            return "Off"
        else:
            return "On"
    else:
    #If it is off, it switches the pin on if it is LESS than the threshold minus two
        if(temperature < (threshold - 2)):
            actuatorPin[pindex].on()
            return "On"
        else:
            return "Off"



#Purpose: Finds a specified query from a given URL after being fed the starting character and designated ending character. This function assumes all queries have unique ascii starting characters.
#Parameters: str URL: Full current URL string
#             char query_start_indicator: The character that denotes the start of your query string segment. Will not be included in the taken string.
#             char query_end_indicator: The character that denotes the end of your query string segment. Will not be included in the taken string.
#Return: Returns a truncated int that is the extracted value from the specified URL query.

# def get_url_query(URL, query_start_indicator, query_end_indicator):
    
#     querystring = ""
    
#     #means that the current character is between the start and end indicator
#     inQuery = False
    
#     for char in URL:
#         if (char == query_start_indicator):
#             inQuery = True
#         elif (char == query_end_indicator):
#             break
        
#         if (inQuery):
#             querystring += char
    
#     #now you have the query string, so find the equals sign in the query string
#     querystring_as_list = querystring.split("=")
#     query_value = int(float(querystring_as_list[1]))
    
#     return query_value


#Function: vacancy_string
#Purpose: Takes the status of the IR sensor and returns the strings "In Use" or "Vacant" for use in the HTML.
#Parameters: Takes the detection status of the IR sensors.
#Return: Returns "In Use" if the IR says the shower is in use, and "Vacant" otherwise.
def vacancy_string(IR_input):
    if(IR_input):
        return "In Use"
    else:
        return "Vacant"


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

def picoHardwareLoop(): #Main hardware-based loop that polls the sensors and updates the actuators!! Lehung/Dr. Chelvan look here!
    #print("Hardware loop!")
    global adcPin
    global m_dataRecord
    global m_bargraph
    global timestamp
    #global obLed
    #print(".")
    pollSensors(0) #maya's sensors
    pollSensors(1) #esme's sensors
    pollSensors(2) #seb's sensors

    global shower1_status
    global shower2_status
    shower1_status = set_heater_status(2, shower_temp_threshold[0], s_Temperature[0]) #Updates the heater status.
    shower2_status = set_heater_status(3, shower_temp_threshold[1], s_Temperature[1])
    
    #Update the bar-graph record with the current average temperature.
    m_dataRecord[timestamp//WEEK_TIMESTEP][timestamp%WEEK_TIMESTEP] = (s_Temperature[0] + s_Temperature[1])/2
    #Calculate the rolling average for the current time ID only. Other values don't need to be recalculated.
    m_ravg = 0.0
    for i in range(RAVG_DEPTH):
        m_ravg += m_dataRecord[i][timestamp%WEEK_TIMESTEP]
    m_bargraph[timestamp%WEEK_TIMESTEP] = m_ravg/RAVG_DEPTH
    timestamp += 1
    
    if(timestamp>=TOTAL_TIME):
        print(m_dataRecord)
        timestamp = 0
    
    #PLACEHOLDER: Update actuators
        
    #PLACEHOLDER: Push results to webpage-exposed API. Note: This might not be necessary; since it's running in a separate thread, the results can be dynamically accessed so long as they're global variables.
    
def get_status(): #Intakes the status of things we want to push to the webpage as a dictionary and then returns it as a json to be pushed. This is the main Pico -> Webpage 'API'; everything we want to automatically update without refreshing the page should be recorded here and updated by JS inside the webpage.
    avg_temp = (s_Temperature[0] + s_Temperature[1])/2
    heater_check = heater_status(shower1_status, shower2_status)
    num_showers = (m_irStatus[0] + m_irStatus[1])
    flow = (e_flowrate[0] + e_flowrate[1])
    status = {
        "temp1": s_Temperature[0],
        "temp2": s_Temperature[1],
        "avg_temp": avg_temp,
        "heater_check": heater_check,
        "num_showers": num_showers,
        "flow": flow,
        "shower_occ0" : shower_occupency[0],
        "shower_occ1" : shower_occupency[1],
        "sh1_heatstatus" : shower1_status,
        "sh2_heatstatus" : shower2_status
    }
    return json.dumps(status)

def web_page(m_data):#Generates the webpage payload. I separated out the style, script, and main body of the HTML into separate strings so we could work with them more easily.
    bar_width = 8
    m_bars_data = []
    m_text_data = []
    for i in range(COARSE_TIMESTEP): #Counts off each day, from 0 to 6.
        dayslice = [m_data[j] for j in range(i*FINE_TIMESTEP,(i+1)*FINE_TIMESTEP)]
        print("Printing bars,", dayslice)
        m_bars_data.append(m_bars_day(dayslice)) #These need to pass m_bars_day and m_peak_day the relevant data from m_bargraph.
        m_text_data.append(m_peak_day(dayslice))
    m_bars_data = "\n".join(m_bars_data) #Terminates the end with a newline.
    m_text_data = "\n".join(m_text_data)
    
    styleblock = """
        .barbox { /*Generic centering class for non-graphic elements of the graph section*/
            text-align: center;
            vertical-align: middle;
        } 
        .bar { /*The bar element of the graph section, gets procedurally generated by python templating*/
            height: 150px;
            width: 8px;
            display: inline-block;
            background-color: #004499;
            padding: 0px;
        } 
        /*Format class for the text data on row 3 of the graph*/
        .bartext {font-family: "Times New Roman", Times, serif;} 
        .box { /* Dictates the colour, width, height alignment of contents, and other relevant details of the black boxes used in the second row of the table */
            border: 2px solid black;
            padding: 10px;
            background-color:white;
            color:black; width:100px;
            height:75px;
            margin: 0 auto;
            align-items:center;
            justify-content:center;
            display:inline-block;
        } 
        
        .sebastian .slider {width: 100%;}
        .sebastian th, .sebastian td {
            padding-left: 20px;
            padding-right: 20px;
        }
    """

    scriptblock = """
        function decTruncate(v) { /*Apparently this is the best way to round to two decimal places using Javascript. I know! Weird language.*/
            return Math.round(v*100)/100;
        }
        function updateStatus() {
            fetch("/status", {
                method: "GET",
                headers: {
                    "Accept": "application/json"
                }
            })
            .then((response) => response.ok ? response.json() : Promise.reject(response))
            .then((data) => {
                document.getElementById("temp1").innerText = decTruncate(data.temp1); /*This bit of the JS updates all of the values we want to have auto-update on the page! This doesn't include the bar graphs; they can't be auto-regenerated but record very long-term data anyway, so the bar graphs auto-updating would be sort of pointless strain on the connection.*/
                document.getElementById("temp2").innerText = decTruncate(data.temp2);
                document.getElementById("avg_temp").innerText = decTruncate(data.avg_temp);
                document.getElementById("heater_check").innerText = data.heater_check;
                document.getElementById("num_showers").innerText = data.num_showers;
                document.getElementById("flow").innerText = decTruncate(data.flow);
                document.getElementById("shower_occ1").innerText = data.shower_occ1;
                document.getElementById("shower_occ2").innerText = data.shower_occ2;
                document.getElementById("sh1_heatstatus").innerText = data.sh1_heatstatus;
                document.getElementById("sh2_heatstatus").innerText = data.sh2_heatstatus;
            });
        }
        setInterval(updateStatus, 1000); // Refresh every 1 second

        const queryParams = window.location.search;
        const URLParams = new URLSearchParams(window.location.search);
        var slider = document.getElementById("threshold1");
        var output = document.getElementById("value1");
        var slider2 = document.getElementById("threshold2");
        var output2 = document.getElementById("value2");
        slider.value = URLParams.get('threshold1');
        slider2.value = URLParams.get('threshold2');

        //For Updating the URL with query parameters:
        function updateURL(){
            var slidervalue1 = document.getElementById("threshold1").value; //These get the threshold values.
            var slidervalue2 = document.getElementById("threshold2").value;

            var baseUrl = window.location.href.split('?')[0]; //This stores the current URL
            var newUrl = baseUrl + "?threshold1=" + encodeURIComponent(slidervalue1) + "&threshold2=" + encodeURIComponent(slidervalue2); //This attaches the threshold values to a new URL

            
            //This updates the URL at the top
            //Maya's note: it updates the URL but didn't actually push the results to the server; for now I'll use replace() to ensure it gets pushed, and I'll try to find a less clunky way to implement it after, if there's time.
            //window.history.pushState({ path: newUrl }, '', newUrl);
            window.location.replace(newUrl);

        }

        //updateURL();

        output.innerHTML = slider.value;
        output2.innerHTML = slider2.value;

        slider.oninput = function() {
            output.innerHTML = this.value;
        }

        slider2.oninput = function() {
            output2.innerHTML = this.value;
        }

        slider.addEventListener("change",(event) => {updateURL();});
        slider2.addEventListener("change",(event) => {updateURL();});
    """
    html = """
    <html>
        <head>
            <title>Pico Web Server</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <link rel="icon" href="data:,">
            <style>
                {styleblock}
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
                    <span id="avg_temp"></span>&deg;C <!--The temperature data from the thermistor is displayed here-->
                    </div>
                </td>
                <td>
                    <div style="font-size:170%" class="box"> <!--Div for the heater status, declares font size and adds box-->
                    <span id="heater_check"></span> <!--States whether the heater is on/off-->
                    </div>
                </td>
                <td>
                    <div style="font-size:170%" class="box"> <!--Div for the number of showers currently in use, declares font size and adds box-->
                    <span id="num_showers"></span><!--The IR sensor detects how many showers are in use and that number is displayed here-->
                    </div>
                </td>
                <td>
                    <div style="font-size:170%" class="box"> <!--Div for the current water usage, declares font size and adds box-->
                    <span id="flow"></span> L/min <!--Amount of water being used in L/min, will be calculated using data from photoresistor-->
                    </div>
                </td>
                
            </table>

            <!-- Maya's HTML Section -->
            <table border = "1" width = 75%> <!--Beginning of table containing the graph-->
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

            <div class="sebastian" style="background-color:#DDDDDD">
                <h3>The following section is restricted to technicians only:</h3>
                <!--<center>-->

                <!--Shower 1 info table here.-->  
                <table>
                    <tr>
                        <th><h3>Shower 01</h3></th>
                    </tr>
                    <tr>
                        <td>Status:</td>
                        <td><span id="shower_occ1"></span></td> <!--One of these will be selected depending on the IR status-->  
                        <td style="text-align:center;">HOT Threshold</td> 
                    </tr>
                    <tr>
                        <td></td>
                    </tr>
                    <tr>
                        <td>Water Temperature:</td>
                        <td><span id="temp1"></span>&#176;C</td><!--This is where the temperature of the water for the current shower will go-->  
                        <td><input type="range" min="0" max="50" value="40" class="slider" id="threshold1">10&#176;C <span style="float:right">50&#176;C</span></td>
                    
                        <!--Later, this and other sliders like it will relay the selected value back to the pico to change the threshold that enables the inline heating system-->  
                    
                        <td style="border:1px solid black;"><span id="value1"></span>&#176;C</td> 
                    
                    
                    <!--This is where the value of the current HOT threshold for the shower is, based on the slider selection-->
                    
                    </tr>
                    <tr>
                        <td></td>
                    </tr>
                    <tr>
                        <td>Heater Status:</td>
                        <td><span id="sh1_heatstatus"></span></td> <!--One of these will be selected based on the heater status, which may be its own variable or extrapolated based on current temperature and threshold. I believe the former is more appropriate-->  
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
                        <td><span id="shower_occ2"></span></td>
                        <td style="text-align:center;">HOT Threshold</td>
                    </tr>
                    <tr>
                        <td></td>
                    </tr>
                    <tr>
                        <td>Water Temperature:</td>
                        <td><span id="temp2"></span>&#176;C</td>
                        
                        <td><input type="range" min="0" max="50" value="40" class="slider" id="threshold2">10&#176;C <span style="float:right">50&#176;C</span></td>
                        
                        <td style="border:1px solid black;"><span id="value2"></span>&#176;C</td>
                    </tr>
                    <tr>
                        <td></td>
                    </tr>
                    <tr>
                        <td>Heater Status:</td>
                        <td><span id="sh2_heatstatus"></span></td>
                    </tr>
                </table>  
                <!--</center>-->
                <br>
                <br>
                <br>
            </div>

            <script>
                {scriptblock}
            </script>
        </body>
    </html>
    """.format(styleblock = styleblock, scriptblock = scriptblock, m_bars_data=m_bars_data,m_text_data = m_text_data, bar_width=bar_width)
    return html

def send_response(conn, headers, body, max_attempts = 10): #A function that handles the apparent inability of the Pico to send the entire webpage in one go. It'll keep track of how much gets sent with each attempt, and keep going until there's no more to push. If it takes too many attempts, it fails.
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
    
def process_request(request): #An HTTP header interpreter to enable us to pull out the query parameters as integers, and throws an error if it encounters difficulty.
    response = ""

    # print(request)
    global shower_temp_threshold
    if request["path"] == "/":
        print("getting webpage")
        for k, v in request["query"]:
            if k == "threshold1":
                shower_temp_threshold[0] = int(v)
            if k == "threshold2":
                shower_temp_threshold[1] = int(v)
        body = web_page(m_bargraph)
        headers = ["HTTP/1.1 200 OK", "Content-Type: text/html", "Content-Length: {}".format(len(body)), "Connection: close"]
        response = "\n".join(headers) + "\n\n" + body

    elif request["path"] == "/status":
        print("getting status")
        body = get_status()
        headers = ["HTTP/1.1 200 OK", "application/json", "Content-Length: {}".format(len(body)), "Connection: close"]
        response = "\n".join(headers) + "\n\n" + body
    else:
        response = "HTTP/1.1 404 Not Found\n\n"
    return response

def respond_request(socket): #Connect to the socket and kick back connection information to the console.
    try:
        conn, addr = socket.accept()
    except OSError as e:
        if e.errno == 110:
            return
        else:
            raise

    print('Got a connection from {}'.format(addr))

    try:
        # Pump bytes from the buffer until we have the whole request (usually just one pass)
        recv_bufsize = 1024
        reqdata = b""
        chunk = conn.recv(recv_bufsize)
        while chunk:
            reqdata += chunk
            if len(chunk) == recv_bufsize:
                chunk = conn.recv(recv_bufsize)
            else:
                chunk = None

        # If the request was empty, just skip it completely
        if not reqdata:
            return None
        
        # UTF-8 is the accepted language of the web
        reqdata = reqdata.decode("UTF-8")
        reqdata = reqdata.replace("\r\n", "\n")
        
        # print('Request Content = {}'.format(reqdata))

        request = {} #Breaks down the contents of request as a dictionary for interpretation, and passes that to process_request above.
        reqline, _, reqdata = reqdata.partition("\n")
        reqline = reqline.split(" ")
        request["method"] = reqline[0]
        request["fullpath"] = reqline[1]
        request["path"], _, request["querystr"] = request["fullpath"].partition("?")
        request["query"] = []
        if request["querystr"]:
            for param in request["querystr"].split("&"):
                k, _, v = param.partition("=")
                request["query"].append((k, v.strip(" ")))
        request["protocol"] = reqline[2]

        headerstr, _, request["body"] = reqdata.partition("\n\n")

        request["headers"] = []
        for line in headerstr.split("\n"):
            k, _, v = line.partition(":")
            request["headers"].append((k, v.strip(" ")))

        response = process_request(request).encode("UTF-8")
        sentlen = 0
        while sentlen < len(response):
            sentlen += conn.send(response[sentlen:])
        print("Sent {} bytes response.".format(sentlen))
    except OSError as e:
        if e.errno == 110:
            return
        else:
            raise
    finally:
        conn.close()
    return
    
    
#Seb's new global variables:
threshold_q_start_indi = ["?","&"] #index 0 for shower 1, index 1 for shower 2
shower_temp_threshold = [25,25]
shower_actuator_pindex = [actuatorPin[2],actuatorPin[3]]
shower_occupency = ["Vacant", "Vacant"]
shower1_heater_status = "Off"
shower2_heater_status = "Off"

def main(): #The main loop. It just makes me feel better to put this in a function. Doesn't it make you feel better, too?
    global shutdown
    print("Booting up...")

    watchdog = machine.WDT(timeout=5000) #The Pico kept crashing into a weird unreachable state where I'd have to power cycle it, so now when the Pico encounters a problem it'll just time out and hard-reset itself, no problem.
    print("Created Watchdog timer")

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
    s.settimeout(0.1)
    s.listen(5)
    
    next_hardware_update = utime.ticks_ms()
    while not shutdown:
        try:
            watchdog.feed()
            respond_request(s)
            #print(utime.ticks_ms())
            if utime.ticks_diff(next_hardware_update, utime.ticks_ms()) < 0: #Triggers the hardware loop once per second or so (it's lagged slightly by s.settimeout). 
                print("Hardware update...")
                picoHardwareLoop()
                next_hardware_update = utime.ticks_ms() + 1000
                gc.collect() #Clean up unused memory. This code, when run on a Pi Pico W, will run into memory allocation failures without it, and hard fault.
        except KeyboardInterrupt:
            print("Shutting down...")
            shutdown = True
    s.close() #This single command makes sure the socket closes when you're done using the Pico.
    
main() #Sets all of the above code into motion.


