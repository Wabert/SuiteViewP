' Module: mdlDataSourceConnections.bas
' Type: Standard Module
' Stream Path: VBA/mdlDataSourceConnections
' =========================================================

Attribute VB_Name = "mdlDataSourceConnections"
Option Explicit
Private dctODBC As Dictionary
Private mblnConnectionProblems As Boolean
Private blnInitialized As Boolean
Private dctFields As Dictionary
Private Const COMM_FAIL_ERROR_NBR = -2147467259 ' Err.Descriptoin [DataDirect][ODBC Shadow driver][DB2]Communication link failure.

Private Sub InitializeConnectDictionary()
    Set dctFields = New Dictionary
    Set dctODBC = New Dictionary
    blnInitialized = True
End Sub

'==================================================================================================================================
'ODBC AND QUERY RESULTS
'==================================================================================================================================
Private Function GetRecordset(sql As String, sRegion As String) As ADODB.Recordset
    
   
    
    If Not (blnInitialized) Then InitializeConnectDictionary
    Dim blnConnect As Boolean
    
    'Load new connection if needed
    If Not dctODBC.exists(sRegion) Then LoadNewConnection (sRegion)
    Dim k
    Set k = dctODBC(sRegion)
   
    Dim DataSet As ADODB.Recordset
    Set DataSet = New ADODB.Recordset
    
    
    
    'If there is an error in the using the connection (Communication link), refresh the connection and try one more time
    On Error Resume Next
    
    Err.Clear
    
    DataSet.Open sql, dctODBC(sRegion)
 
    'This error can occur when computer falls asleep while the app is open and then you try to get a policy
    If Err.Number <> 0 Then
        Debug.Print "GetRecordset Error 1: " & Err.Number & " - " & Err.Description
        If Err.Number = COMM_FAIL_ERROR_NBR Then
            'If is error occurs, refresh the odbc and try one more time
            dctODBC.Remove (sRegion)
            LoadNewConnection (sRegion)
    
            Err.Cear
            DataSet.Open sql, dctODBC(sRegion)
            If Err.Number <> 0 Then Debug.Print "GetRecordset Error 2: " & Err.Number & " - " & Err.Description
        End If
    End If
            
    
    If DataSet.BOF And DataSet.EOF Then
        Debug.Print sql
        Debug.Print "No data found."
    Else
        DataSet.MoveFirst
        'DataSet.MoveLast
    End If
    
    Set GetRecordset = DataSet
    
    On Error GoTo 0
    
    Set DataSet = Nothing

End Function

Public Sub LoadNewConnection(sRegion)
        
        'Clear out any existing connection
        If dctODBC.exists(sRegion) Then dctODBC.Remove (sRegion)
        
        'Establish and open connection
        On Error GoTo ErrorHandler

        Dim cn As ADODB.Connection
        Set cn = New ADODB.Connection
        cn.ConnectionString = GetConnectionString(sRegion, True)
        cn.Open
        Set dctODBC(sRegion) = cn
        
        On Error GoTo 0
        
        Exit Sub

ErrorHandler:
    Dim Errorstatement As String
    Errorstatement = "From LoadNewConnection.   Err.Number " & Err.Number & " | Err.Description " & Err.Description & " | Err.Source " & Err.Source
    Debug.Print Errorstatement
    On Error GoTo 0
End Sub

Private Function GetConnectionString(ByVal strDataSource As String, Optional blnUseNEON = False)
Dim tempString As String


'If this attempt is trying to use the NEON connection on the local machine, then add the "NEON" prefix
'to the DataSource name so it can be selected below.  But only add the NEON string if trying to connect
'to one of the Cyberlife Regions - CKAS, CKMO or CKPR.
If left(strDataSource, 2) = "CK" Then
    If blnUseNEON Then strDataSource = "NEON_" & strDataSource
End If

Select Case strDataSource
'  Case enumDataSource.SQLServer: tempString = "Provider=SQLOLEDB; " + "Data Source=" + mServerReference + "; " + "Initial Catalog=" + mDataBaseReference + "; " + "Integrated Security = SSPI;"
'  Case enumDataSource.MSAccess:    tempString = "Provider=Microsoft.Jet.OLEDB.4.0;Data Source=" & mDataBaseReference & ";"
'  Case "CKPR":    tempString = "DRIVER={DataDirect Shadow Client 7.3}; APNA=ADHOCUSER; APPL=ODBC; BYDB=Yes; CPFX=SHADOW; DBTY=DB2; DTCH=Yes; HOST=prodesa; LINK=TCPIP; NEONTRACE=INFO LOG=c:\neonlog.txt; PLAN=SDBC1010; PORT=1200; SUBSYS=DSN; TSCH=Yes; USERPARM=DRDA; WATR=No;"
'  Case "CKMO":    tempString = "DRIVER={DataDirect Shadow Client 7.3}; APNA=ADHOCUSER; APPL=ODBC; BYDB=Yes; CPFX=SHADOW; DBTY=DB2; DTCH=Yes; HOST=devlesa; LINK=TCPIP; NEONTRACE=INFO LOG=c:\neonlog.txt; PLAN=SDBC1010; PORT=1200; SUBSYS=DSNM; TSCH=Yes; USERPARM=DRDA; WATR=No;"
'  Case "CKAS":    tempString = "DRIVER={DataDirect Shadow Client 7.3}; APNA=ADHOCUSER; APPL=ODBC; BYDB=Yes; CPFX=SHADOW; DBTY=DB2; DTCH=Yes; HOST=devlesa; LINK=TCPIP; NEONTRACE=INFO LOG=c:\neonlog.txt; PLAN=SDBC1010; PORT=1200; SUBSYS=DSNT; TSCH=Yes; USERPARM=DRDA; WATR=No;"
'
  'Case "UL_Rates":  tempString = "Provider=SQLOLEDB; Data Source='dsul_ratesdev'; Initial Catalog='ul_rates'; Integrated Security = SSPI;"
  Case "UL_Rates":  tempString = "Data Source=" + "UL_Rates"
  Case "NEON_CKPR":    tempString = "Data Source=" + "NEON_DSN"
  Case "NEON_CKMO":    tempString = "Data Source=" + "NEON_DSNM"
  Case "NEON_CKAS":    tempString = "Data Source=" + "NEON_DSNT"
  Case "NEON_CKCS":    tempString = "Data Source=" + "NEON_DSNT"
  Case "NEON_CKSR":    tempString = "Data Source=" + "NEON_DSNT"
End Select

GetConnectionString = tempString
End Function

Public Function FetchTable(QueryStatements As String, DataSource As String, Optional blnAddHeaders = True) As Variant
'This function is used to retrieve data from a database and store it in an array.
'The function takes three parameters: "QueryStatements" which is the SQL query used to retrieve the data,
'"DataSource" which specifies the connection to the database and "blnAddHeaders" which is an optional parameter that, when set to true,
'adds field names as headers to the top of the array. The function uses ADODB (ActiveX Data Objects) to create a recordset and execute the query.
'It then uses the "GetRows" method to retrieve the data into an array, and if blnAddHeaders is true,
'it adds field names as headers to the top of the array. The function then returns the array as a variant.

    'Open Recordset
    Dim DataSet As ADODB.Recordset
    Dim dataArray As Variant
    
    'On Error GoTo EmptySetErrorHandler

        
        '9/1/2021 - RJH.    I got a new computer with MS Office 365; my old computer had Office 2016.
        '                   For some reason the query wouldn't run and I kept getting an "Automation Error".
        '                   I was able to figure out that the query would run only if it contained a "WITH" statement.
        '                   I have no idea why this works but it does.
        '                   So to every query that does not contain a "WITH" statement I add a benign "WITH" clause.
        
        If DataSource = "CKAS" Or DataSource = "CKMO" Or DataSource = "CKPR" Or DataSource = "CKSR" Or DataSource = "CKCS" Then
            If left(QueryStatements, 4) <> "WITH" Then QueryStatements = "WITH DUMBY AS (SELECT 1 FROM DB2TAB.LH_COV_PHA) " & QueryStatements
        End If
        
        'Debug.Print QueryStatements
        
        Set DataSet = GetRecordset(QueryStatements, DataSource)
        
        If DataSet.EOF And DataSet.BOF Then
            dataArray = Empty
            
        Else
            'Get recordset data into array
            
            dataArray = DataSet.GetRows
            dataArray = Transpose2DArray_to_2DArray(dataArray)
        
        
            If blnAddHeaders Then
            
                'Create a dictionary of field names.  this will be used to easily get an array of field names
                Dim dctFlds As Dictionary
                Dim fld As Variant
                Dim NonceNum As Integer 'If to avoid dublicate names in dctFlds a number may be appended to make the name unique
                
                Set dctFlds = New Dictionary
                For Each fld In DataSet.Fields
                    NonceNum = NonceNum + 1
                    If dctFlds.exists(fld.name) Then
                        dctFlds.Add fld.name & NonceNum, fld.name & NonceNum
                    Else
                        dctFlds.Add fld.name, fld.name
                    End If
                Next
        
                'Add Field names to the top of the DataArray
                Call InsertRowIntoArray(dataArray, LBound(dataArray), dctFlds.Keys)
            
            End If
        End If
            
        FetchTable = dataArray
        Set DataSet = Nothing
        
'    On Error GoTo 0
    
'    Exit Function
  
'EmptySetErrorHandler:
'    Set DataSet = Nothing
'    Dim Errorstatement As String
'    Errorstatement = "From FetchTable.   Err.Number " & Err.Number & " | Err.Descriptoin " & Err.Description & " | Err.Source " & Err.Source
'    'MsgBox Errorstatement, vbOKCancel
'    Debug.Print QueryStatements
'    Debug.Print "FetchTable: " & Errorstatement
'    On Error GoTo 0
End Function


Public Function SQLStringForRegion(sqlstring As String, DB2_Source As String)
Dim tempstr As String
 Select Case DB2_Source
   Case "CKAS": tempstr = Replace(sqlstring, "DB2TAB.", "UNIT.", , , vbTextCompare)
   Case "CKCS": tempstr = Replace(sqlstring, "DB2TAB.", "CYBERTEK.", , , vbTextCompare)
   Case "CKSR": tempstr = Replace(sqlstring, "DB2TAB.", "CKSR.", , , vbTextCompare)
   Case Else: tempstr = sqlstring
 End Select
 SQLStringForRegion = tempstr
End Function

Public Function Transpose2DArray_to_2DArray(ary) As Variant
'The WorksheetFunction.Transpose function will convert a 2D array to a 1D array if input array only has one row.
'This can cause problems later on with functions expecting a 2D array.  So this function is created to
'always transpose a 2D array into another 2D array
Dim temparray() As Variant
Dim X As Long, Y As Long
ReDim temparray(LBound(ary, 2) To UBound(ary, 2), LBound(ary, 1) To UBound(ary, 1))
For X = LBound(ary, 1) To UBound(ary, 1)
 For Y = LBound(ary, 2) To UBound(ary, 2)
    temparray(Y, X) = ary(X, Y)
 Next
Next
Transpose2DArray_to_2DArray = temparray
End Function
