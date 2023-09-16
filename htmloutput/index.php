
<?php
print "<img src='MPYCbanner.png'>";
print "<h2> Results 23/24 </h2>";
$files = glob("23*.htm"); 
$stack = glob("24*.htm");
$files = array_merge($files,$stack);
rsort($files);
foreach ($files as $key => $file)
if (($key >= $_GET["page"] * 10) && ($key < ($_GET["page"] +1) *10))
print "<div class='fileicon'>
           <a href='$file'>
               <p class='filetext'>$key: $file</p>
           </a>
      </div>";;
$total = count($files) / 10;
$i = 0;
print "<p> Page:";
while ($i <= $total):
    print "<a href='?page=$i'> $i</a>";
    $i++;
endwhile;
print "<h2> Season Championship </h2>";
print "<a href='leaguetable2324.htm'> League Table</a><br>";
print "<a href='pointstable2324.htm'> Points Table</a><br>";
print "<h2> Historical Season Tables </h2>";
print "<a href='archive'>Archive</a>";
?>
