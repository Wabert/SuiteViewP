' Module: Module1.bas
' Type: Standard Module
' Stream Path: VBA/Module1
' =========================================================

Attribute VB_Name = "Module1"
Function GetDB2TableNames() As Collection
    Dim rs As Object, tableNames As New Collection
    Dim cn As ADODB.Connection
    
    Set conn = New ADODB.Connection
    ' Create ADODB connection object
    
    ' Open connection using DSN and credentials
    conn.Open "Data Source=NEON_DSN"
    
    
    'This gives you a list of all the schemas
    sql = "SELECT DISTINCT CREATOR FROM SYSIBM.SYSTABLES"
    
    
    'The schema we use is 'DB2TAB '.  So this will give you a list of all the tables
    sql = "WITH DUMBY AS (SELECT 1 FROM DB2TAB.LH_COV_PHA) SELECT NAME FROM SYSIBM.SYSTABLES WHERE CREATOR = 'DB2TAB '"
    
    ' Query DB2 system catalog for table names in a specific schema
    'Set rs = conn.Execute(sql)
    
    Dim DataSet As ADODB.Recordset
    Set DataSet = New ADODB.Recordset
    
    DataSet.Open sql, conn
    
    If DataSet.EOF And DataSet.BOF Then
        Stop
    End If
    dataArray = DataSet.GetRows
    
    
    ' Collect table names
    Do While Not DataSet.EOF
        tableNames.Add DataSet.Fields("TABNAME").value
        DataSet.MoveNext
    Loop
    
    ' Clean up
    DataSet.Close
    conn.Close
    
    Set GetDB2TableNames = tableNames
End Function

' Example usage
Sub TestGetDB2TableNames()
    Dim tables As Collection, tblName As Variant
    Set tables = GetDB2TableNames()
    
    For Each tblName In tables
        Debug.Print tblName
    Next tblName
End Sub

